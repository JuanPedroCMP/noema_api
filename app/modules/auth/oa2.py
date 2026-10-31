from fastapi import APIRouter, Depends, HTTPException, status

from ...core.security import oauth2_scheme

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])


@router.get("/link", deprecated=True)
def retired_server_side_google_oauth(
    token: str = Depends(oauth2_scheme),
) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "google_oauth_flow_retired",
            "message": "Use the native Google SDK and POST the verified grant to /api/v1/google_drive/account/link.",
        },
    )


@router.get("/callback", deprecated=True)
def retired_google_oauth_callback() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "google_oauth_flow_retired",
            "message": "Google account linking now uses the native app OAuth flow.",
        },
    )
