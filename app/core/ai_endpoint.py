import ipaddress
import os
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException, status


def validate_ai_endpoint(base_url: str) -> None:
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    allow_local = os.getenv("AI_ALLOW_LOCAL_AI", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }

    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not hostname
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provider URL must not contain credentials, a query, or a fragment.",
        )

    is_local_hostname = (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "host.docker.internal"
    )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None

    is_loopback = is_local_hostname or (
        address is not None and address.is_loopback
    )
    is_allowed_local_ip = (
        allow_local and address is not None and address.is_private
    )
    if is_loopback and not allow_local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Local AI endpoints require AI_ALLOW_LOCAL_AI=true on the API server.",
        )
    if (
        address is not None
        and not address.is_global
        and not is_loopback
        and not is_allowed_local_ip
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Private and reserved IP addresses are not allowed as provider endpoints.",
        )

    if address is None and not is_local_hostname:
        try:
            resolved_addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(
                    hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Provider hostname could not be resolved.",
            ) from exc
        if not resolved_addresses or any(
            not resolved_address.is_global
            for resolved_address in resolved_addresses
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Provider hostname must resolve only to public IP addresses.",
            )

    if parsed.scheme != "https" and not (
        allow_local and (is_loopback or is_allowed_local_ip)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provider endpoints must use HTTPS. HTTP is allowed only for local AI.",
        )
