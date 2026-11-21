import os

import uvicorn


def _positive_int_setting(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer.") from exc
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer.")
    return parsed


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=_positive_int_setting("WEB_CONCURRENCY", 1),
        limit_concurrency=_positive_int_setting(
            "UVICORN_LIMIT_CONCURRENCY", 100
        ),
    )


if __name__ == "__main__":
    main()
