import os
from dotenv import load_dotenv
from semanticscholar import SemanticScholar
from googleapiclient.discovery import build
from tavily import TavilyClient

load_dotenv(dotenv_path='app/config/.env.api_utils')

ss_api_key = os.getenv("SS_API")
yt_api_key = os.getenv("YT_API")
books_api_key = os.getenv("BOOKS_API")
tavily_api_key = os.getenv("TAVILY_API")

ss = SemanticScholar(api_key=ss_api_key)
clientTavily = TavilyClient(tavily_api_key)

def getPapers(query: str):
    result = ss.search_paper(query=query)
    print(result.raw_data)   
    return result.raw_data


def getVideos(termo_busca: str, max_resultados: int = 10):
    # Constrói o serviço da API do YouTube
    youtube = build("youtube", "v3", developerKey=yt_api_key)
    
    # Executa a busca
    requisicao = youtube.search().list(
        part="snippet",
        q=termo_busca,
        type="video",
        maxResults=max_resultados
    )
    resposta = requisicao.execute()
    
    # Processa os resultados
    for item in resposta.get("items", []):
        titulo = item["snippet"]["title"]
        video_id = item["id"]["videoId"]
        canal = item["snippet"]["channelTitle"]
        
        print(resposta)

        print(f"Título: {titulo}")
        print(f"Canal: {canal}")
        print(f"Link: https://youtube.com/watch?v={video_id}")
        print("-" * 40)
    return resposta.get("items", [])
 
def getSearchResuls(query: str):
    # To install: pip install tavily-python  
    response = clientTavily.search(
        query=query,
        search_depth="advanced",
        max_results=15,
        include_usage=True
    )
    print(response)
    return response

def getBooks(termo_busca: str):  
    # Inicializa o serviço para a API 'books' na versão 'v1'
    # Se tiver uma chave, use: build('books', 'v1', developerKey='SUA_CHAVE_AQUI')
    servico = build('books', 'v1', developerKey=books_api_key)
    
    # Cria a requisição de busca
    requisicao = servico.volumes().list(q=termo_busca, maxResults=15)
    
    # Executa a requisição e armazena a resposta
    resposta = requisicao.execute()
    
    print(f"Total de itens encontrados: {resposta.get('totalItems', 0)}\n")
    
    # Processa os resultados
    for item in resposta.get('items', []):
        info = item.get('volumeInfo', {})
        titulo = info.get('title', 'Título não informado')
        autores = ", ".join(info.get('authors', ['Autor desconhecido']))
        
        print(f"Título: {titulo}")
        print(f"Autor(es): {autores}")
        print("-" * 40)
    return resposta.get("items", [])