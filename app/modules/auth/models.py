from pydantic import BaseModel

class LoginData(BaseModel):
    login_identificator: str
    password: str