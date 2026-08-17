from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.user.router import router as user_router
from app.modules.ai.router import router as ai_router
from app.modules.theme.router import router as user_theme_router
from app.modules.device.router import router as device_router
from app.modules.user_config.router import router as user_config_router
from app.modules.google_drive.router import router as google_drive_router
from app.modules.log.router import router as log_router
from app.modules.ai_provider.router import router as ai_provider_router

api_router= APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(ai_router)
api_router.include_router(user_theme_router)
api_router.include_router(device_router)
api_router.include_router(user_config_router)
api_router.include_router(google_drive_router)
api_router.include_router(log_router)
api_router.include_router(ai_provider_router)





