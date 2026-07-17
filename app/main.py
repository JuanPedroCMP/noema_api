from fastapi import FastAPI

from .api.api import api_router

app = FastAPI(title="Noemapip install pwdlib[argon2]API", version="1.0")

@app.get("/")
def root():
    return{"message": "funcionando normalmelte!"}

app.include_router(api_router)