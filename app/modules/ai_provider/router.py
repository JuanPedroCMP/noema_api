from fastapi import APIRouter, Depends, HTTPException
from app.modules.ai_provider.services.services import getBooks, getPapers, getSearchResuls, getVideos
from .services.ai_compatibility_layer import AiProvider
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
    result = ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt)
    return result

@router.post("/get_materials")
def get_materials(user_prompt: str, agent_id: UUID, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ai_provider = AiProvider(db=db, user_token=token)
    result = ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt) ## Gerar o pronpt para cada pesquisa TODO: Fazer modelo pydantic para gerar os dados
    ## Pega o pronpt e faz cada pesquisa
    ## A IA filtra os resultados relevantes (retorna os id's)
    ## Coloca todos os resultados num modelo pydantic 
    return



### TESTES
@router.post("/teste_papers")
def use_ai(query: str, token: str = Depends(oauth2_scheme)):
    return getPapers(query=query)

@router.post("/teste_yt")
def use_ai(query: str, token: str = Depends(oauth2_scheme)):
    return getVideos(termo_busca=query)

@router.post("/teste_books")
def use_ai(query: str, token: str = Depends(oauth2_scheme)):
    return getBooks(termo_busca=query)

@router.post("/teste_pesquisa")
async def use_ai(query: str, token: str = Depends(oauth2_scheme)): 
    return await getSearchResuls(query=query)