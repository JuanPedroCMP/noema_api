import os

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .db_models.app_auth_models import User
from .security import get_current_user, oauth2_scheme


def require_admin(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().casefold()
    if not admin_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrative access is not configured.",
        )

    user = get_current_user(token, db)
    if user.primary_email.strip().casefold() != admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative access required.",
        )
    return user
