from ...core.db_models.ai_models import AiProvider, AiModel, UserApiKey, Agent, TaskType, AgentModel, UserApiKeyCanUseIaModel, AiUsageLog
from ...core.security import get_current_user, encrypt_api_key, decrypt_api_key
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import ProviderCreate, ProviderUpdate, AiModelCreate, AiModelUpdate, UserApiKeyCreate, UserApiKeyUpdate, AgentCreate, AgentUpdate, AgentFilters, AgentModelCreate, AgentModelUpdate, AgentModelFilters, UserApiKeyCanUseIaModelCreate, UserApiKeyCanUseIaModelFilters, AiUsageLogFilters, AiUsageLogCreate
from datetime import datetime

################
### Provider
################
def get_provider(identificator : str, db: Session):
    provider = AiProvider()
    try:  
        provider = db.scalar(select(AiProvider).where(
                AiProvider.id == UUID(identificator),
        ))
    except:
        provider = db.scalar(select(AiProvider).where(
                AiProvider.slug == identificator
        ))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider não encontrado")
        
    return provider

def list_providers(db: Session, filters: dict | None) -> list[AiProvider]:
    stmt = select(AiProvider)
    for k, v in filters.items():
        collum_attr = getattr(AiProvider, k)
        stmt = stmt.where(collum_attr == v)
    
    providers = db.scalars(stmt).all()
    
    if providers is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider não encontrado")
        
    return providers

def create_provider(provider_data: ProviderCreate, db: Session) -> AiProvider:
    new_provider = AiProvider(
        id=uuid4(),
        slug=provider_data.slug,
        display_name=provider_data.display_name,
        base_url=provider_data.base_url,
        is_active=True,
        created_at=datetime.now()
    )
    
    db.add(new_provider)
    db.commit()
    db.refresh(new_provider)
    return new_provider

def update_provider(identificator : str, provider_data: ProviderUpdate, db: Session) -> AiProvider:
    provider = get_provider(identificator, db)
    
    for k, v in provider_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(provider, k, v)
    provider.updated_at = datetime.now()
    db.commit()
    db.refresh(provider)
    return provider

def delete_provider(identificator : str, db: Session) -> bool:
    provider = get_provider(identificator, db)
    db.delete(provider)
    db.commit()
    return True


################
### AI Model
################
def get_ai_model(identificator : str, db: Session):
    ai_model = AiModel()
    try:  
        ai_model = db.scalar(select(AiModel).where(
                AiModel.id == UUID(identificator),
        ))
    except:
        ai_model = db.scalar(select(AiModel).where(
                AiModel.slug == identificator
        ))
    if ai_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modelo de Ia não encontrado")
        
    return ai_model

def list_ai_models(db: Session, filters: dict | None) -> list[AiModel]:
    stmt = select(AiModel)
    for k, v in filters.items():
        collum_attr = getattr(AiModel, k)
        stmt = stmt.where(collum_attr == v)
    
    ai_models = db.scalars(stmt).all()
    
    if ai_models is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modelo de Ia não encontrado")
        
    return ai_models

def create_ai_model(ai_model_data: AiModelCreate, db: Session) -> AiModel:
    new_ai_model = AiModel(
        id=uuid4(),
        slug=ai_model_data.slug,
        id_ai_provider=ai_model_data.id_ai_provider,
        display_name=ai_model_data.display_name,
        context_window=ai_model_data.context_window,
        input_token_limit=ai_model_data.input_token_limit,
        output_token_limit=ai_model_data.output_token_limit,
        supports_vision=ai_model_data.supports_vision,
        is_active=True,
        created_at=datetime.now() 
    )
    
    db.add(new_ai_model)
    db.commit()
    db.refresh(new_ai_model)
    return new_ai_model

def update_ai_model(identificator : str, provider_data: AiModelUpdate, db: Session) -> AiModel:
    ai_model = get_ai_model(identificator, db)

    for k, v in provider_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(ai_model, k, v)
    ai_model.updated_at = datetime.now()
    db.commit()
    db.refresh(ai_model)
    return ai_model

def delete_ai_model(identificator : str, db: Session) -> bool:
    ai_model = get_ai_model(identificator, db)
    db.delete(ai_model)
    db.commit()
    return True


################
### User API Key
################

def get_user_api_key(token: str, identificator: str, db: Session) -> UserApiKey:
    user_api_key = UserApiKey()
    user = get_current_user(token, db)
    try:
        user_api_key = db.scalar(select(UserApiKey).where(and_(
            UserApiKey.id_user == user.id,
            UserApiKey.id == UUID(identificator)
        ))) 
    except:
        user_api_key = db.scalar(select(UserApiKey).where(and_(
            UserApiKey.id_user == user.id,
            UserApiKey.id == identificator
        ))) 
        
    if user_api_key is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Api Key não encontrada")
     
    return user_api_key

def list_user_api_keys(token: str, filters: dict | None, db: Session) -> list[UserApiKey]:
    user = get_current_user(token, db)
    stmt = select(UserApiKey).where(UserApiKey.id_user == user.id)
    
    for k, v in filters.items():
        attr = getattr(UserApiKey, k)
        stmt = stmt.where(attr == v)
        
    user_api_keys = db.scalars(stmt).all()
    
    return user_api_keys

def create_user_api_key(token: str, create_data: UserApiKeyCreate, db: Session) -> UserApiKey:
    user = get_current_user(token, db)
    new_api_key = UserApiKey(
        id=uuid4(),
        id_ai_provider=create_data.id_ai_provider,
        id_user=user.id,
        name=create_data.name,
        encrypted_key=encrypt_api_key(create_data.api_key),
        is_active=create_data.is_active,
        created_at=datetime.now()
    )
    
    db.add(new_api_key)
    db.commit()
    db.refresh(new_api_key)
    return new_api_key

def update_user_api_key(token: str, identificator: str, upd_data: UserApiKeyUpdate, db: Session) -> UserApiKey:
    upd_api_key = get_user_api_key(token, identificator, db)
    
    for k, v in upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True).items():
        if k == "api_key":
            setattr(upd_api_key, "encrypted_key", upd_api_key)
        else:
            setattr(upd_api_key, k, v)    
    
    upd_api_key.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_api_key)
    return upd_api_key

def delete_user_api_key(token: str, identificator: str, db: Session) -> bool:
    del_api_key = get_user_api_key(token, identificator, db)
    db.delete(del_api_key)
    db.commit()
    return True

################
### Ai Agent
################
def get_agent(identificator: str, db: Session) -> Agent:

    agent = db.scalar(select(Agent).where(
        Agent.id == UUID(identificator)
    ))
        
    if agent is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agente não encontrado")
     
    return agent

def list_agents(filters: AgentFilters | None, db: Session) -> list[Agent]:
    stmt = select(Agent)
    
    for k, v in filters.items():
        attr = getattr(Agent, k)
        stmt = stmt.where(attr == v)
        
    agents = db.scalars(stmt).all()
    
    return agents

def creaate_agent(create_data: AgentCreate, db: Session) -> Agent:
    new_agent= Agent(
        id=uuid4(),
        alias=create_data.alias,
        task=create_data.task,
        base_system_prompt=create_data.base_system_prompt,
        temperature=create_data.temperature,
        created_at=datetime.now()
    )
    
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent

def update_agent(identificator: str, upd_data: AgentUpdate, db: Session) -> Agent:
    upd_agent = get_agent(identificator, db)
    
    for k, v in upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True).items():
        setattr(upd_agent, k, v)    
    
    upd_agent.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_agent)
    return upd_agent

def delete_agent(identificator: str, db: Session) -> bool:
    del_agent = get_agent(identificator, db)
    db.delete(del_agent)
    db.commit()
    return True


################
### Agent Model
################
def get_agent_model(identificator: str, db: Session) -> AgentModel:

    agent_model = db.scalar(select(AgentModel).where(
        AgentModel.id == UUID(identificator)
    ))

    if agent_model is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agente_Modelo de Ia não encontrado")
     
    return agent_model

def list_agent_models(filters: AgentModelFilters | None, db: Session) -> list[AgentModel]:
    stmt = select(AgentModel)
    
    for k, v in filters.items():
        attr = getattr(AgentModel, k)
        stmt = stmt.where(attr == v)
        
    agent_models = db.scalars(stmt).all()
    
    return agent_models

def create_agent_model(create_data: AgentModelCreate, db: Session) -> AgentModel:
    new_agent_model= AgentModel(
        id=uuid4(),
        id_agent=create_data.id_agent,
        id_ai_model=create_data.id_ai_model,
        quality_expected=create_data.quality_expected,
        custom_system_prompt=create_data.custom_system_prompt,
        custom_temperature=create_data.temperature,
        created_at=datetime.now()
    )
    
    db.add(new_agent_model)
    db.commit()
    db.refresh(new_agent_model)
    return new_agent_model

def update_agent_model(identificator: str, upd_data: AgentModelUpdate, db: Session) -> AgentModel:
    upd_agent_model = get_agent_model(identificator, db)
    
    for k, v in upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True).items():
        setattr(upd_agent_model, k, v)    
    
    upd_agent_model.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_agent_model)
    return upd_agent_model

def delete_agent_model(identificator: str, db: Session) -> bool:
    del_agent_model = get_agent_model(identificator, db)
    db.delete(del_agent_model)
    db.commit()
    return True

################
### User api key can use ia model
################
def get_user_api_key_can_use_ia_model(identificator: str, db: Session, token: str) -> UserApiKeyCanUseIaModel:
    user = get_current_user(token, db)

    user_api_key_can_use_ia_model = db.scalar(select(UserApiKeyCanUseIaModel)
        .join(
            UserApiKey, UserApiKey.id == UserApiKeyCanUseIaModel.id_user_api_key
        )
        .where(
            UserApiKeyCanUseIaModel.id == UUID(identificator),
            UserApiKey.id_user == user.id
    ))

    if user_api_key_can_use_ia_model is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relação não encontrada")
     
    return user_api_key_can_use_ia_model

def list_user_api_key_can_use_ia_model(filters: UserApiKeyCanUseIaModelFilters | None, db: Session, token: str) -> list[UserApiKeyCanUseIaModel]:
    user = get_current_user(token, db)
    stmt = select(UserApiKeyCanUseIaModel).join(
         UserApiKey, UserApiKey.id == UserApiKeyCanUseIaModel.id_user_api_key
        ).where(UserApiKey.id_user == user.id)  
    
    for k, v in filters.items():
        attr = getattr(UserApiKeyCanUseIaModel, k)
        stmt = stmt.where(attr == v)
        
    user_api_key_can_use_ia_models = db.scalars(stmt).all()
    
    return user_api_key_can_use_ia_models

def create_user_api_key_can_use_ia_model(create_data: UserApiKeyCanUseIaModelCreate, db: Session, token: str) -> UserApiKeyCanUseIaModel:
    user = get_current_user(token, db)
   
    obj_key = get_user_api_key(token, create_data.id_user_api_key, db)
    
    if obj_key.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    obj_ai_model = get_ai_model(create_data.id_ai_model, db)
    
    if obj_ai_model.id_ai_provider != obj_key.id_ai_provider:
        raise HTTPException(400, "Modelo de Ia e Key de providers diferents")
    
    new_user_api_key_can_use_ia_model= UserApiKeyCanUseIaModel(
        id=uuid4(),
        id_ai_model=create_data.id_ai_model,
        id_user_api_key=create_data.id_user_api_key,
        created_at=datetime.now()
    )    
    
    db.add(new_user_api_key_can_use_ia_model)
    db.commit()
    db.refresh(new_user_api_key_can_use_ia_model)
    return new_user_api_key_can_use_ia_model

def delete_user_api_key_can_use_ia_model(identificator: str, db: Session, token: str ) -> bool:
    user = get_current_user(token, db)
   
    uap_can_use_ai_model = get_user_api_key_can_use_ia_model(identificator, db, token)
    obj_key = get_user_api_key(token, uap_can_use_ai_model.id_user_api_key , db)
    
    if obj_key.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    del_user_api_key_can_use_ia_model = get_user_api_key_can_use_ia_model(identificator, db, token)
    db.delete(del_user_api_key_can_use_ia_model)
    db.commit()
    return True

################
### Ai Log
################
def get_ai_usage_log(identificator: str, db: Session, token: str) -> AiUsageLog:
    user = get_current_user(token, db)

    ai_usage_log = db.scalar(select(AiUsageLog)
        .join(
            UserApiKey, UserApiKey.id == AiUsageLog.id_user_api_key
        )
        .where(
            AiUsageLog.id == UUID(identificator),
            UserApiKey.id_user == user.id
    ))
        
    if ai_usage_log is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relação não encontrada")
     
    return ai_usage_log

def list_ai_usage_logs(filters: AiUsageLogFilters | None, db: Session, token: str) -> list[AiUsageLog]:
    user = get_current_user(token, db)
    stmt = select(AiUsageLog)
    
    stmt = stmt.where(AiUsageLog.id_user == user.id)
    
    for k, v in filters.items():
        attr = getattr(AiUsageLog, k)
        stmt = stmt.where(attr == v)
        
    ai_usage_logs = db.scalars(stmt).all()
    
    return ai_usage_logs

def create_ai_usage_log(create_data: AiUsageLogCreate, db: Session, token: str) -> AiUsageLog:
    user = get_current_user(token, db)
    
    if create_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
 
    new_ai_usage_log= AiUsageLog(
        id=uuid4(),
        id_agent_model=create_data.id_agent_model,
        id_user=create_data.id_user,
        usage_details=create_data.usage_datails,
        created_at=datetime.now()
    )    
    
    db.add(new_ai_usage_log)
    db.commit()
    db.refresh(new_ai_usage_log)
    return new_ai_usage_log