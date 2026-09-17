from urllib.parse import urlencode
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
import secrets

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

