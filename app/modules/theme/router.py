from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from ...core.db_models.ai_models import TaskType
from .services import update_user_color_theme as uuct, update_user_typography_theme as uutt, create_user_color_theme as cuct, create_user_typography_theme as cutt, delete_user_color_theme as duct, delete_user_typography_theme as dutt, get_user_color_theme as guct, get_user_typography_theme as gutt, list_user_color_themes as luct, list_user_typography_themes as lutt
from .models import UserColorThemeCreate, UserColorThemeFilters, UserColorThemeOut,UserColorThemeUpdate,UserTypographyThemeCreate,UserTypographyThemeFilters,UserTypographyThemeOut,UserTypographyThemeUpdate
from typing import Annotated

router = APIRouter(
    prefix="/user_theme",
)

#################
### User Color Theme
################
color_theme_router = APIRouter(
    prefix="/color_theme",
    tags=["color_theme"]
)

@color_theme_router.get("/get/{identificator}", response_model=UserColorThemeOut)
def get_color_theme(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return guct(token, identificator, db)

@color_theme_router.get("/list", response_model=list[UserColorThemeOut])
def list_color_theme(filters: Annotated[UserColorThemeFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return luct(token, db, _filters)

@color_theme_router.post("/create", response_model=UserColorThemeOut)
def create_color_theme(new_user_color_theme: UserColorThemeCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_color_theme = cuct(token, new_user_color_theme, db)
    return user_color_theme

@color_theme_router.put("/update/{identificator}", response_model=UserColorThemeOut)
def update_color_theme(identificator: str, user_color_theme_data: UserColorThemeUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uuct(token, identificator, user_color_theme_data, db)
    return upd_data

@color_theme_router.delete("/delete/{identificator}")
def delete_color_theme(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = duct(token, identificator, db)
    return sucess

#################
### User Typography Theme
################
typography_theme_router = APIRouter(
    prefix="/typography_theme",
    tags=["typography_theme"]
)

@typography_theme_router.get("/get/{identificator}", response_model=UserTypographyThemeOut)
def get_typography_theme(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gutt(identificator, db, token)

@typography_theme_router.get("/list", response_model=list[UserTypographyThemeOut])
def list_typography_theme(filters: Annotated[UserTypographyThemeFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lutt(db, _filters, token)

@typography_theme_router.post("/create", response_model=UserTypographyThemeOut)
def create_typography_theme(new_user_typography_theme: UserTypographyThemeCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_typography_theme = cutt(new_user_typography_theme, db, token)
    return user_typography_theme

@typography_theme_router.put("/update/{identificator}", response_model=UserTypographyThemeOut)
def update_typography_theme(identificator: str, user_typography_theme_data: UserTypographyThemeUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uutt(identificator, user_typography_theme_data, db, token)
    return upd_data

@typography_theme_router.delete("/delete/{identificator}")
def delete_typography_theme(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = dutt(identificator, db, token)
    return sucess

router.include_router(color_theme_router)
router.include_router(typography_theme_router)