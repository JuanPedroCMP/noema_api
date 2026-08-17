from fastapi import APIRouter, Depends, HTTPException
from .ai_compatibility_layer import AiProvider
from sqlalchemy.orm import Session
from ...core.database import get_db
from ...core.security import oauth2_scheme
from uuid import UUID

router = APIRouter(
    prefix="/ai_router",
    tags=["ai_router"]
)

@router.post("/use_ai")
def use_ai(user_prompt: str, agent_id: UUID, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ai_provider = AiProvider(db=db, user_token=token)
    ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt)
    return
