from ...core.db_models.theme_models import UserColorTheme, UserTypographyTheme
from ...core.security import get_current_user, encrypt_api_key, decrypt_api_key
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import UserColorThemeCreate, UserTypographyThemeUpdate, UserColorThemeUpdate, UserTypographyThemeCreate
from datetime import datetime

################
### User Color Theme
################
def get_user_color_theme(token: str, identificator : str, db: Session):
    color_theme = UserColorTheme()
    try:  
        color_theme = db.scalar(select(UserColorTheme).where(
                UserColorTheme.id == UUID(identificator),
        ))
    except:
        color_theme = db.scalar(select(UserColorTheme).where(
                UserColorTheme.name == identificator
        ))
        
    user = get_current_user(token, db)

    if color_theme.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    if color_theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return color_theme

def list_user_color_themes(token: str, db: Session, filters: dict | None) -> list[UserColorTheme]:
    stmt = select(UserColorTheme)
    user = get_current_user(token, db)

    stmt = stmt.where(UserColorTheme.id_user == user.id)
    
    for k, v in filters.items():
        collum_attr = getattr(UserColorTheme, k)
        stmt = stmt.where(collum_attr == v)
    
    color_themes = db.scalars(stmt).all()
    
    if color_themes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return color_themes

def create_user_color_theme(token: str, color_theme_data: UserColorThemeCreate, db: Session) -> UserColorTheme:
    user = get_current_user(token, db)
    
    if color_theme_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    new_user_color_theme = UserColorTheme(
        id=uuid4(),
        id_user=color_theme_data.id_user,
        name=color_theme_data.name,
        seed_color=color_theme_data.seed_color,
        override_json=color_theme_data.override_json,
        created_at=datetime.now()
    )
    
    db.add(new_user_color_theme)
    db.commit()
    db.refresh(new_user_color_theme)
    return new_user_color_theme

def update_user_color_theme(token: str, identificator : str, color_theme_data: UserColorThemeUpdate, db: Session) -> UserColorTheme:
    color_theme = get_user_color_theme(token, identificator, db)
    
    user = get_current_user(token, db)
    
    if color_theme_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
 
    
    for k, v in color_theme_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(color_theme, k, v)
    color_theme.updated_at = datetime.now()
    db.commit()
    db.refresh(color_theme)
    return color_theme

def delete_user_color_theme(token: str, identificator : str, db: Session) -> bool:
    color_theme = get_user_color_theme(token, identificator, db)
    user = get_current_user(token, db)

    if color_theme.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    db.delete(color_theme)
    db.commit()
    return True

################
### User Typography Theme
################
def get_user_typography_theme(identificator : str, db: Session, token: str):
    typography_theme = UserTypographyTheme()
    try:  
        typography_theme = db.scalar(select(UserTypographyTheme).where(
                UserTypographyTheme.id == UUID(identificator),
        ))
    except:
        typography_theme = db.scalar(select(UserTypographyTheme).where(
                UserTypographyTheme.name == identificator
        ))
    
    user = get_current_user(token, db)
    
    if typography_theme.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
        
    if typography_theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return typography_theme

def list_user_typography_themes(db: Session, filters: dict | None, token: str) -> list[UserTypographyTheme]:
    user = get_current_user(token, db)
    stmt = select(UserTypographyTheme)
    
    stmt = stmt.where(UserTypographyTheme.id_user == user.id)
    
    for k, v in filters.items():
        collum_attr = getattr(UserTypographyTheme, k)
        stmt = stmt.where(collum_attr == v)
    
    typography_themes = db.scalars(stmt).all()
    
    if typography_themes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return typography_themes

def create_user_typography_theme(typography_theme_data: UserTypographyThemeCreate, db: Session, token: str) -> UserTypographyTheme:
    user = get_current_user(token, db)
    
    if typography_theme_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
 
    
    new_user_typography_theme = UserTypographyTheme(
        id=uuid4(),
        id_user=typography_theme_data.id_user,
        name=typography_theme_data.name,
        display_font=typography_theme_data.display_font,
        body_font=typography_theme_data.body_font,
        mono_font=typography_theme_data.mono_font,
        override_json=typography_theme_data.override_json,
        created_at=datetime.now()
    )
    
    db.add(new_user_typography_theme)
    db.commit()
    db.refresh(new_user_typography_theme)
    return new_user_typography_theme

def update_user_typography_theme(identificator : str, typography_theme_data: UserTypographyThemeUpdate, db: Session, token: str) -> UserTypographyTheme:
    typography_theme = get_user_typography_theme(identificator, db, token)
    
    for k, v in typography_theme_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(typography_theme, k, v)
    typography_theme.updated_at = datetime.now()
    db.commit()
    db.refresh(typography_theme)
    return typography_theme

def delete_user_typography_theme(identificator : str, db: Session, token: str) -> bool:
    typography_theme = get_user_typography_theme(identificator, db, token)
    user = get_current_user(token, db)

    if typography_theme.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    db.delete(typography_theme)
    db.commit()
    return True