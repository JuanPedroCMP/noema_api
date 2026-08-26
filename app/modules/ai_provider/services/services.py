import os
from dotenv import load_dotenv
from semanticscholar import SemanticScholar

load_dotenv(dotenv_path='app/config/.env.api_utils')

ss_api_key = os.getenv("SS_API")

ss = SemanticScholar(api_key=ss_api_key)

def getPapers(query: str):
    ss.search_paper(query=query)
    return

def getVideos():
    return

def getSearchResuls():
    return

def getBooks():
    return
