from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from ...core.db_models.ai_models import TaskType
from .services import get_provider as gp, list_providers as lp, create_provider as cp, update_provider as up, delete_provider as dp, get_ai_model as gam, list_ai_models as lam, create_ai_model as cam, update_ai_model as uam, delete_ai_model as dam,  get_user_api_key as guak, list_user_api_keys as luak, create_user_api_key as cuak, update_user_api_key as uuak, delete_user_api_key as duak, update_agent as ua, get_agent as ga, creaate_agent as ca, delete_agent as da, list_agents as la, get_agent_model as gaml, list_agent_models as laml, create_agent_model as caml, update_agent_model as uaml, delete_agent_model as daml, delete_user_api_key_can_use_ia_model as duapkcuam, list_user_api_key_can_use_ia_model as luapkcuam, get_user_api_key_can_use_ia_model as guapkcuam, create_user_api_key_can_use_ia_model as cuapkcuam, create_ai_usage_log as caul, get_ai_usage_log as gaul, list_ai_usage_logs as laul
from .models import ProviderOut, ProviderFilters, ProviderCreate, ProviderUpdate, AiModelUpdate, AiModelOut, AiModelCreate, AiModelFilters, UserApiKeyCreate, UserApiKeyFilters, UserApiKeyOut,UserApiKeyUpdate, AgentOut, AgentCreate, AgentUpdate, AgentFilters, AgentModelCreate, AgentModelOut, AgentModelFilters, AgentModelUpdate, UserApiKeyCanUseIaModelCreate, UserApiKeyCanUseIaModelFilters, UserApiKeyCanUseIaModelOut, AiUsageLogFilters, AiUsageLogOut, AiUsageLogCreate
from typing import Annotated

router = APIRouter(
    prefix="/ai",
)



################
### Provider
################
provider_router = APIRouter(
    prefix="/provider",
    tags=["provider"]
)

### Obs.: Percebi que a função de listar faz o que esta função faz, mas é tarde demais, já fiz todos os endpoints (╯°□°）╯︵ ┻━┻
@provider_router.get("/get/{identificator}", response_model=ProviderOut)
def get_provider(identificator: str, db: Session = Depends(get_db)):
    return gp(identificator, db)

@provider_router.get("/list", response_model=list[ProviderOut])
def list_providers(filters: Annotated[ProviderFilters, Query()], db: Session = Depends(get_db)):
    
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lp(db, _filters)

@provider_router.post("/create", response_model=ProviderOut)
def create_provider(new_provider: ProviderCreate, db: Session = Depends(get_db)):
    provider = cp(new_provider, db)
    return provider

@provider_router.put("/update/{identificator}", response_model=ProviderOut)
def update_provider(identificator: str, provider_data: ProviderUpdate, db: Session = Depends(get_db)):
    upd_data = up(identificator, provider_data, db)
    return upd_data

@provider_router.delete("/delete/{identificator}")
def delete_provider(identificator: str, db: Session = Depends(get_db)):
    sucess = dp(identificator, db)
    return sucess

################
### ai_model
################
ai_model_router = APIRouter(
    prefix="/ai_model",
    tags=["ai_model"]
)

@ai_model_router.get("/get/{identificator}", response_model=AiModelOut)
def get_ai_model(identificator: str, db: Session = Depends(get_db)):
    return gam(identificator, db)

@ai_model_router.get("/list", response_model=list[AiModelOut])
def list_ai_models(filters: Annotated[AiModelFilters, Query()], db: Session = Depends(get_db)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lam(db, _filters)

@ai_model_router.post("/create", response_model=AiModelOut)
def create_ai_model(new_ai_model: AiModelCreate, db: Session = Depends(get_db)):
    ai_model = cam(new_ai_model, db)
    return ai_model

@ai_model_router.put("/update/{identificator}", response_model=AiModelOut)
def update_ai_model(identificator: str, ai_model_data: AiModelUpdate, db: Session = Depends(get_db)):
    upd_data = uam(identificator, ai_model_data, db)
    return upd_data

@ai_model_router.delete("/elete/{identificator}")
def delete_ai_model(identificator: str, db: Session = Depends(get_db)):
    sucess = dam(identificator, db)
    return sucess

################
### User API Key
################
user_api_key_router = APIRouter(
    prefix="/user_api_key",
    tags=["user_api_key"]
)

@user_api_key_router.get("/get/{identificator}", response_model=UserApiKeyOut)
def get_user_api_key(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return guak(token, identificator, db)

@user_api_key_router.get("/list", response_model=list[UserApiKeyOut])
def list_user_api_key(filters: Annotated[UserApiKeyFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return luak(token, _filters, db)

@user_api_key_router.post("/create", response_model=UserApiKeyOut)
def create_user_api_key(new_ai_model: UserApiKeyCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    ai_model = cuak(token, new_ai_model, db)
    return ai_model

@user_api_key_router.put("/update/{identificator}", response_model=UserApiKeyOut)
def update_user_api_key(identificator: str, ai_model_data: UserApiKeyUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uuak(token, identificator, ai_model_data, db)
    return upd_data

@user_api_key_router.delete("/delete/{identificator}")
def delete_user_api_key(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = duak(token, identificator, db)
    return sucess

################
### Agent
################
agent_router = APIRouter(
    prefix="/agent",
    tags=["agent"]
)

@agent_router.get("/get/{identificator}", response_model=AgentOut)
def get_agent(identificator: str, db: Session = Depends(get_db)):
    return ga(identificator, db)

@agent_router.get("/list", response_model=list[AgentOut])
def list_agent(filters: Annotated[AgentFilters, Query()], db: Session = Depends(get_db)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return la(_filters, db)

@agent_router.post("/create", response_model=AgentOut)
def create_agent(new_agent: AgentCreate, db: Session = Depends(get_db)):
    agent = ca(new_agent, db)
    return agent

@agent_router.put("/update/{identificator}", response_model=AgentOut)
def update_agent(identificator: str, agent_data: AgentUpdate, db: Session = Depends(get_db)):
    upd_data = ua(identificator, agent_data, db)
    return upd_data

@agent_router.delete("/delete/{identificator}")
def delete_agent(identificator: str, db: Session = Depends(get_db)):
    sucess = da(identificator, db)
    return sucess

################
### Agent Model
################
agent_model_router = APIRouter(
    prefix="/agent_model",
    tags=["agent_model"]
)

@agent_model_router.get("/get/{identificator}", response_model=AgentModelOut)
def get_agent_model(identificator: str, db: Session = Depends(get_db)):
    return gaml(identificator, db)

@agent_model_router.get("/list", response_model=list[AgentModelOut])
def list_agent_model(filters: Annotated[AgentModelFilters, Query()], db: Session = Depends(get_db)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return laml(_filters, db)

@agent_model_router.post("/create", response_model=AgentModelOut)
def create_agent_model(new_agent_model: AgentModelCreate, db: Session = Depends(get_db)):
    agent_model = caml(new_agent_model, db)
    return agent_model

@agent_model_router.put("/update/{identificator}", response_model=AgentModelOut)
def update_agent_model(identificator: str, agent_model_data: AgentModelUpdate, db: Session = Depends(get_db)):
    upd_data = uaml(identificator, agent_model_data, db)
    return upd_data

@agent_model_router.delete("/delete/{identificator}")
def delete_agent_model(identificator: str, db: Session = Depends(get_db)):
    sucess = daml(identificator, db)
    return sucess

################
### User api key can use ia model
################
user_api_key_can_use_ia_model_router = APIRouter(
    prefix="/user_api_key_can_use_ia_model",
    tags=["user_api_key_can_use_ia_model"]
)

@user_api_key_can_use_ia_model_router.get("/get/{identificator}", response_model=UserApiKeyCanUseIaModelOut)
def get_agent_model(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return guapkcuam(identificator, db, token)

@user_api_key_can_use_ia_model_router.get("/list", response_model=list[UserApiKeyCanUseIaModelOut])
def list_agent_model(filters: Annotated[UserApiKeyCanUseIaModelFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return luapkcuam(_filters, db, token)

@user_api_key_can_use_ia_model_router.post("/create", response_model=UserApiKeyCanUseIaModelOut)
def create_agent_model(new_agent_model: UserApiKeyCanUseIaModelCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    agent_model = cuapkcuam(new_agent_model, db, token)
    return agent_model

@user_api_key_can_use_ia_model_router.delete("/delete/{identificator}")
def delete_agent_model(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = duapkcuam(identificator, db, token)
    return sucess


################
### Ai Usage Log
################
ai_usage_log_router = APIRouter(
    prefix="/ai_usage_log",
    tags=["ai_usage_log"]
)

@ai_usage_log_router.get("/get/{identificator}", response_model=AiUsageLogOut)
def get_agent_model(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gaul(identificator, db, token)

@ai_usage_log_router.get("/list", response_model=list[AiUsageLogOut])
def list_agent_model(filters: Annotated[AiUsageLogFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return laul(_filters, db, token)

@ai_usage_log_router.post("/create", response_model=AiUsageLogOut)
def create_agent_model(new_agent_model: AiUsageLogCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    agent_model = caul(new_agent_model, db, token)
    return agent_model



router.include_router(provider_router)
router.include_router(ai_model_router)
router.include_router(user_api_key_router)
router.include_router(agent_router)
router.include_router(agent_model_router)
router.include_router(user_api_key_can_use_ia_model_router)
router.include_router(ai_usage_log_router)
