from ...core.db_models.user_config_models import UserGlobalConfig, UserLocalConfig, Language, ResponseLanguagePreferenceOrder
from ...core.security import get_current_user
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import UserGlobalConfigCreate, UserGlobalConfigUpdate, UserLocalConfigCreate, UserLocalConfigUpdate, LanguageUpdate, LanguageCreate, ResponseLanguagePreferenceOrderCreate, ResponseLanguagePreferenceOrderUpdate
from datetime import datetime

################
### User Global Config
################
def get_user_global_config(token: str, identificator : str, db: Session):
    user_global_config = db.scalar(select(UserGlobalConfig).where(
                UserGlobalConfig.id == UUID(identificator),
    ))
    
    if user_global_config is None:
        user_global_config = db.scalar(select(UserGlobalConfig).where(
                UserGlobalConfig.id_user == UUID(identificator),
        ))
    
    user = get_current_user(token, db)

    if user_global_config.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    if user_global_config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config não encontrada")
        
    return user_global_config

def create_user_global_config(token: str, user_global_config_data: UserGlobalConfigCreate, db: Session) -> UserGlobalConfig:
    user = get_current_user(token, db)
    
    if user_global_config_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    new_user_global_config = UserGlobalConfig(
        id=uuid4(),
        id_user=user_global_config_data.id_user,
        id_language=user_global_config_data.id_language,
        id_user_color_theme=user_global_config_data.id_user_color_theme,
        id_user_typography_theme=user_global_config_data.id_user_typography_theme,
        preferences=user_global_config_data.preferences,
        created_at=datetime.now()
    )
    
    db.add(new_user_global_config)
    db.commit()
    db.refresh(new_user_global_config)
    return new_user_global_config

def update_user_global_config(token: str, identificator : str, user_global_config_data: UserGlobalConfigUpdate, db: Session) -> UserGlobalConfig:
    user_global_config = get_user_global_config(token, identificator, db)
    
    for k, v in user_global_config_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(user_global_config, k, v)
    user_global_config.updated_at = datetime.now()
    db.commit()
    db.refresh(user_global_config)
    return user_global_config


################
### User Local Config
################
def get_user_local_config(token: str, identificator : str, db: Session):
    user_local_config = db.scalar(select(UserLocalConfig).where(
        UserLocalConfig.id == UUID(identificator),
    ))

        
    user = get_current_user(token, db)

    if user_local_config.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    if user_local_config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config Local não encontrada")
        
    return user_local_config

def list_user_global_configs(token: str, db: Session, filters: dict | None) -> list[UserLocalConfig]:
    stmt = select(UserLocalConfig)
    user = get_current_user(token, db)

    stmt = stmt.where(UserLocalConfig.id_user == user.id)
    
    for k, v in filters.items():
        collum_attr = getattr(UserLocalConfig, k)
        stmt = stmt.where(collum_attr == v)
    
    user_global_configs = db.scalars(stmt).all()
    
    if user_global_configs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nehuma Config Local não encontrada")
        
    return user_global_configs


def create_user_local_config(token: str, user_local_config_data: UserLocalConfigCreate, db: Session) -> UserLocalConfig:
    user = get_current_user(token, db)
    
    if user_local_config_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    new_user_local_config = UserLocalConfig(
        id=uuid4(),
        id_user=user_local_config_data.id_user,
        id_device=user_local_config_data.id_device,
        id_language=user_local_config_data.id_language,
        id_user_color_theme=user_local_config_data.id_user_color_theme,
        id_user_typography_theme=user_local_config_data.id_user_typography_theme,
        preferences=user_local_config_data.preferences,
        created_at=datetime.now()
    )
    
    db.add(new_user_local_config)
    db.commit()
    db.refresh(new_user_local_config)
    return new_user_local_config

def update_user_local_config(token: str, identificator : str, user_local_config_data: UserLocalConfigUpdate, db: Session) -> UserLocalConfig:
    user_local_config = get_user_local_config(token, identificator, db)
    
    for k, v in user_local_config_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(user_local_config, k, v)
    user_local_config.updated_at = datetime.now()
    db.commit()
    db.refresh(user_local_config)
    return user_local_config


################
### Language
################
def get_language(identificator : str, db: Session):
    language = db.scalar(select(Language).where(
        Language.id == UUID(identificator),
    ))        
        
    if language is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config Local não encontrada")
        
    return language

def list_language(db: Session, filters: dict | None) -> list[Language]:
    stmt = select(Language)
        
    for k, v in filters.items():
        collum_attr = getattr(Language, k)
        stmt = stmt.where(collum_attr == v)
    
    user_global_configs = db.scalars(stmt).all()
    
    if user_global_configs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nehuma Config Local não encontrada")
        
    return user_global_configs


def create_language(language_data: LanguageCreate, db: Session) -> Language:

    new_language = Language(
        id=uuid4(),
        name=language_data.name,
        percentage_translated=language_data.percentage_translated,
        verified_translation=language_data.verified_translation,
        automatic_translation=language_data.automatic_translation,
        created_at=datetime.now()
    )
    
    db.add(new_language)
    db.commit()
    db.refresh(new_language)
    return new_language

def update_language(identificator : str, language_data: LanguageUpdate, db: Session) -> Language:
    language = get_language(identificator, db)
    
    for k, v in language_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(language, k, v)
    language.updated_at = datetime.now()
    db.commit()
    db.refresh(language)
    return language

################
### Response Language Preference Order
################
def get_response_language_preference_order(token: str, identificator : str, db: Session):
    response_language_preference_order = db.scalar(select(ResponseLanguagePreferenceOrder).where(
                ResponseLanguagePreferenceOrder.id == UUID(identificator),
    ))
    
    if response_language_preference_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    user = get_current_user(token, db)

    if response_language_preference_order.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    return response_language_preference_order

def list_response_language_preference_orders(token: str, db: Session, filters: dict | None) -> list[ResponseLanguagePreferenceOrder]:
    stmt = select(ResponseLanguagePreferenceOrder)
    
    user = get_current_user(token, db)

    stmt = stmt.where(ResponseLanguagePreferenceOrder.id_user == user.id)
    
    for k, v in filters.items():
        collum_attr = getattr(ResponseLanguagePreferenceOrder, k)
        stmt = stmt.where(collum_attr == v)
    
    response_language_preference_orders = db.scalars(stmt).all()
    
    if response_language_preference_orders is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nehuma Config Local não encontrada")
        
    return response_language_preference_orders

def create_response_language_preference_order(token: str, response_language_preference_order_data: ResponseLanguagePreferenceOrderCreate, db: Session) -> ResponseLanguagePreferenceOrder:
    user = get_current_user(token, db)
    
    if response_language_preference_order_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
     
    new_response_language_preference_order = ResponseLanguagePreferenceOrder(
        id=uuid4(),
        id_user=response_language_preference_order_data.id_user,
        id_language=response_language_preference_order_data.id_language,
        preference_order=response_language_preference_order_data.preference_order,
    )
    
    db.add(new_response_language_preference_order)
    db.commit()
    db.refresh(new_response_language_preference_order)
    return new_response_language_preference_order

def update_response_language_preference_order(token: str, identificator : str, response_language_preference_order_data: ResponseLanguagePreferenceOrderUpdate, db: Session) -> ResponseLanguagePreferenceOrder:
    response_language_preference_order = get_response_language_preference_order(token, identificator, db)
    
    for k, v in response_language_preference_order_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(response_language_preference_order, k, v)
    db.commit()
    db.refresh(response_language_preference_order)
    return response_language_preference_order

def delete_response_language_preference_order(token: str, identificator : str, db: Session) -> bool:
    response_language_preference_order = get_response_language_preference_order(token, identificator, db)

    db.delete(response_language_preference_order)
    db.commit()
    return True