from fastapi import APIRouter, Depends, HTTPException
from app.modules.ai_provider.models import ExternalResourcesOut, GbBook, S2SearchResult, SearchQueries, TavilyResponse, YtSearchResult
from app.modules.ai_provider.services.services import getBooks, getPapers, getSearchResuls, getVideos
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

@router.post("/use_ai")
def use_ai(user_prompt: str, agent_id: UUID, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ai_provider = AiProvider(db=db, user_token=token)
    result = ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt)
    return result

@router.post("/get_materials")
async def get_materials(user_prompt: str, agent_id: UUID, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ai_provider = AiProvider(db=db, user_token=token)
    result : SearchQueries = ai_provider.call_ai(agent_id = agent_id, user_prompt = user_prompt) ## Gerar o pronpt para cada pesquisa TODO: Fazer modelo pydantic para gerar os dados
    # ## Pega o pronpt e faz cada pesquisa
    # print(result.paper_query)
    
    # papers_adapter = TypeAdapter(list[S2SearchResult])
    # papers : list[S2SearchResult] = papers_adapter.validate_python(getPapers(result.paper_query))
    
    # videos_adapter = TypeAdapter(list[YtSearchResult])
    # videos : list[YtSearchResult] = videos_adapter.validate_python(getVideos(result.yt_videos_query))
    
    # books_adpter = TypeAdapter(list[GbBook])
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
    
    try:
        papers = getPapers(result.paper_query)
    except Exception as err:
        papers = []
        print(err)
        
    try:
        videos = getVideos(result.yt_videos_query)
    except Exception as err:
        videos = []
        print(err)
        
    try:
        books = getBooks(result.books_query)
    except Exception as err:
        books = []
        print(err)
        
    try:
        research = getSearchResuls(result.search_query)
    except Exception as err:   
        research = []
        print(err)
        

    final_result = (papers, videos, books, research)

    
    print(final_result)
    print(type(final_result))
    ## A IA filtra os resultados relevantes (retorna os id's)
    ## Coloca todos os resultados num modelo pydantic 
    return final_result



### TESTES
@router.post("/teste_papers")
def use1_ai(query: str, token: str = Depends(oauth2_scheme)):
    result = getPapers(query=query)
    print(type(result))
    return result 

@router.post("/teste_yt")
def use2_ai(query: str, token: str = Depends(oauth2_scheme)):
    result = getVideos(termo_busca=query)
    print(type(result))
    return result 

@router.post("/teste_books")
def use3_ai(query: str, token: str = Depends(oauth2_scheme)):
    result = getBooks(termo_busca=query)
    print(type(result))
    return result 

@router.post("/teste_pesquisa")
def use4_ai(query: str, token: str = Depends(oauth2_scheme)): 
    result =  getSearchResuls(query=query)
    print(type(result))
    return result 