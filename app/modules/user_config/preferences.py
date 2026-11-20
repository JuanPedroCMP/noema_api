from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.db_models.user_config_models import UserPreferences
from ...core.security import get_current_user
from .models import UserPreferencesOut, UserPreferencesUpdate


def get_user_preferences(token: str, db: Session) -> UserPreferencesOut:
    user = get_current_user(token, db)
    preferences = db.scalar(
        select(UserPreferences).where(UserPreferences.id_user == user.id)
    )
    if preferences is None:
        return UserPreferencesOut(id_user=user.id, preferences={}, updated_at=None)
    return UserPreferencesOut.model_validate(preferences)


def update_user_preferences(
    token: str,
    preferences_data: UserPreferencesUpdate,
    db: Session,
) -> UserPreferencesOut:
    user = get_current_user(token, db)
    preferences = db.scalar(
        select(UserPreferences)
        .where(UserPreferences.id_user == user.id)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if preferences is None:
        preferences = UserPreferences(
            id_user=user.id,
            preferences=preferences_data.preferences,
            created_at=now,
            updated_at=now,
        )
        db.add(preferences)
    else:
        preferences.preferences = preferences_data.preferences
        preferences.updated_at = now

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        preferences = db.scalar(
            select(UserPreferences)
            .where(UserPreferences.id_user == user.id)
            .with_for_update()
        )
        if preferences is None:
            raise
        preferences.preferences = preferences_data.preferences
        preferences.updated_at = now
        db.commit()

    db.refresh(preferences)
    return UserPreferencesOut.model_validate(preferences)
