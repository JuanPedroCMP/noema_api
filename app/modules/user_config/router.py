from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from .services import get_user_global_config as gugc, create_user_global_config as cugc, update_user_global_config as uugc, get_language as gl, list_language as ll, create_language as cl, update_language as ul, delete_response_language_preference_order as drlpo, get_response_language_preference_order as grlpo, list_response_language_preference_orders as lrlpo, create_response_language_preference_order as crlpo, update_response_language_preference_order as urlpo, update_user_local_config as uulc, get_user_local_config as gulc, create_user_local_config as culc
from .models import UserGlobalConfigCreate, UserGlobalConfigOut, UserGlobalConfigUpdate, UserLocalConfigCreate, UserLocalConfigOut, UserLocalConfigUpdate, LanguageUpdate, LanguageFilters, LanguageCreate, LanguageOut, ResponseLanguagePreferenceOrderOut, ResponseLanguagePreferenceOrderUpdate, ResponseLanguagePreferenceOrderCreate, UserLocalConfigFilters
from typing import Annotated

router = APIRouter(
    prefix="/user_config",
)

################
### User Global Config
################
router_user_global_config = APIRouter(
    prefix="/user_global_config",
    tags=["user_global_config"]
)

@router_user_global_config.get("/get/{identificator}", response_model=UserGlobalConfigOut)
def get_user_global_config(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gugc(token, identificator, db)

@router_user_global_config.post("/create", response_model=UserGlobalConfigOut)
def create_user_global_config(new_user_user_global_config: UserGlobalConfigCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_user_global_config = cugc(token, new_user_user_global_config, db)
    return user_user_global_config

@router_user_global_config.put("/update/{identificator}", response_model=UserGlobalConfigOut)
def update_user_global_config(identificator: str, user_user_global_config_data: UserGlobalConfigUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uugc(token, identificator, user_user_global_config_data, db)
    return upd_data

################
### User Local Config
################
router_user_local_config = APIRouter(
    prefix="/user_local_config",
    tags=["user_local_config"]
)

@router_user_local_config.get("/get/{identificator}", response_model=UserLocalConfigOut)
def get_user_local_config(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gulc(token, identificator, db)

@router_user_local_config.get("/list", response_model=list[UserLocalConfigOut])
def list_user_local_configs(filters: Annotated[UserLocalConfigFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    return lrlpo(token, db, _filters,)

@router_user_local_config.post("/create", response_model=UserLocalConfigOut)
def create_user_local_config(new_user_user_local_config: UserLocalConfigCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_user_local_config = culc(token, new_user_user_local_config, db)
    return user_user_local_config

@router_user_local_config.put("/update/{identificator}", response_model=UserLocalConfigOut)
def update_user_local_config(identificator: str, user_user_local_config_data: UserLocalConfigUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uulc(token, identificator, user_user_local_config_data, db)
    return upd_data

################
### Language
################
language_router = APIRouter(
    prefix="/language",
    tags=["language"]
)

@language_router.get("/get/{identificator}", response_model=LanguageOut)
def get_language(identificator: str, db: Session = Depends(get_db)):
    return gl(identificator, db)

@language_router.get("/list", response_model=list[LanguageOut])
def list_languages(filters: Annotated[LanguageFilters, Query()], db: Session = Depends(get_db)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return ll(db, _filters)

@language_router.post("/create", response_model=LanguageOut)
def create_language(new_user_language: LanguageCreate, db: Session = Depends(get_db)):
    user_language = cl(new_user_language, db)
    return user_language

@language_router.put("/update/{identificator}", response_model=LanguageOut)
def update_language(identificator: str, user_language_data: LanguageUpdate, db: Session = Depends(get_db)):
    upd_data = ul(identificator, user_language_data, db)
    return upd_data

################
### Response Language Preference Order
################
response_response_language_preference_order_router = APIRouter(
    prefix="/response_response_language_preference_order",
    tags=["response_response_language_preference_order"]
)

@response_response_language_preference_order_router.get("/get/{identificator}", response_model=ResponseLanguagePreferenceOrderOut)
def get_response_language_preference_order(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return grlpo(token, identificator, db)

@response_response_language_preference_order_router.get("/list", response_model=list[ResponseLanguagePreferenceOrderOut])
def list_response_language_preference_orders(filters: Annotated[LanguageFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    return lrlpo(token, db, _filters,)

@response_response_language_preference_order_router.post("/create", response_model=ResponseLanguagePreferenceOrderOut)
def create_response_language_preference_order(new_user_response_language_preference_order: ResponseLanguagePreferenceOrderCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_response_language_preference_order = crlpo(token, new_user_response_language_preference_order, db)
    return user_response_language_preference_order

@response_response_language_preference_order_router.put("/update/{identificator}", response_model=ResponseLanguagePreferenceOrderOut)
def update_response_language_preference_order(identificator: str, user_response_language_preference_order_data: ResponseLanguagePreferenceOrderUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = urlpo(token, identificator, user_response_language_preference_order_data, db)
    return upd_data

@response_response_language_preference_order_router.delete("/delete/{identificator}")
def update_response_language_preference_order(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> bool:
    sucess = drlpo(token, identificator, db)
    return sucess

router.include_router(router_user_global_config)
router.include_router(router_user_local_config)
router.include_router(language_router)
router.include_router(response_response_language_preference_order_router)
