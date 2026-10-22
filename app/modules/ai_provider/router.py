import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from app.modules.ai_provider.models import ExternalResourcesOut, GbBook, S2SearchResult, SearchQueries, TavilyResponse, YtSearchResult
from app.modules.ai_provider.services.services import (
    get_books,
    get_papers,
    get_search_results,
    get_videos,
)
from .services.ai_compatibility_layer import AiProvider
from sqlalchemy.orm import Session
from ...core.database import get_db
from ...core.security import oauth2_scheme
from uuid import UUID
from pydantic import TypeAdapter

router = APIRouter(
    prefix="/ai_router",
    tags=["ai_router"]
)
logger = logging.getLogger(__name__)

@router.post("/use_ai")
async def use_ai(user_prompt: str, agent_id: UUID, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ai_provider = AiProvider(db=db, user_token=token)
    result = await ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt)
    return result

@router.post("/get_materials")
async def get_materials(
    user_prompt: str,
    agent_id: UUID,
    include_videos: bool = Query(True, alias="get_videos"),
    include_books: bool = Query(True, alias="get_books"),
    include_papers: bool = Query(True, alias="get_papers"),
    include_web: bool = Query(True, alias="get_web"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    ai_provider = AiProvider(db=db, user_token=token)
    result : SearchQueries = await ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt) ## Gerar o pronpt para cada pesquisa TODO: Fazer modelo pydantic para gerar os dados
    # ## Pega o pronpt e faz cada pesquisa
    # print(result.paper_query)
    
    # papers_adapter = TypeAdapter(list[S2SearchResult])
    # papers : list[S2SearchResult] = papers_adapter.validate_python(getPapers(result.paper_query))
    
    # videos_adapter = TypeAdapter(list[YtSearchResult])
    # videos : list[YtSearchResult] = videos_adapter.validate_python(getVideos(result.yt_videos_query))
    
    # books_adpter = TypeAdapter(list[GbBook])j
    # books : list[GbBook] = books_adpter.validate_python(getBooks(result.books_query))
    
    # research = TavilyResponse(**getSearchResuls(result.search_query))
   
        
    # print(type(papers))
    # print(papers)
    
    # print(type(videos))
    # print(videos)
        
    # print(type(books))
    # print(books)
            
    # print(type(research))
    # print(research)
    
    # final_result: ExternalResourcesOut = ExternalResourcesOut(books=books, papers=papers, search_results=research, yt_videos=videos)
    # print(type(final_result))
    # print(final_result)
    async def run_search(search_name: str, search_operation):
        try:
            return await search_operation
        except Exception:
            logger.warning("%s search failed.", search_name, exc_info=True)
            return []

    search_tasks = [
        run_search("paper", get_papers(result.paper_query))
        if include_papers
        else asyncio.sleep(0, result=[]),
        run_search("video", get_videos(result.yt_videos_query))
        if include_videos
        else asyncio.sleep(0, result=[]),
        run_search("book", get_books(result.books_query))
        if include_books
        else asyncio.sleep(0, result=[]),
        run_search("web", get_search_results(result.search_query))
        if include_web
        else asyncio.sleep(0, result=[]),
    ]
    papers, videos, books, research = await asyncio.gather(*search_tasks)
    final_result = (papers or [], videos or [], books or [], research or [])

    ## A IA filtra os resultados relevantes (retorna os id's)
    ## Coloca todos os resultados num modelo pydantic 
    return final_result



### TESTES
@router.post("/get_papers")
async def use1_ai(query: str, token: str = Depends(oauth2_scheme)):
    return await get_papers(query=query)

@router.post("/get_yt")
async def use2_ai(query: str, token: str = Depends(oauth2_scheme)):
    return await get_videos(query=query)

@router.post("/get_books")
async def use3_ai(query: str, token: str = Depends(oauth2_scheme)):
    return await get_books(query=query)

@router.post("/get_pesquisa")
async def use4_ai(query: str, token: str = Depends(oauth2_scheme)):
    return await get_search_results(query=query)