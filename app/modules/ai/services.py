from ...core.db_models.ai_models import AiProvider, AiModel, UserApiKey, Agent, AgentModel, UserApiKeyCanUseIaModel, AiUsageLog
from ...core.security import decrypt, get_current_user, encrypt
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import ProviderCreate, ProviderUpdate, AiModelCreate, AiModelUpdate, UserApiKeyCreate, UserApiKeyUpdate, AgentCreate, AgentUpdate, AgentFilters, AgentModelCreate, AgentModelUpdate, AgentModelFilters, UserApiKeyCanUseIaModelCreate, UserApiKeyCanUseIaModelFilters, AiUsageLogFilters, AiUsageLogCreate
from datetime import datetime

################
### Provider
################
def get_provider(
    identificator: UUID | str,
    db: Session,
    owner_id: UUID | None = None,
    include_inactive: bool = False,
) -> AiProvider:
    visibility = AiProvider.id_user.is_(None)
    if owner_id is not None:
        visibility = or_(visibility, AiProvider.id_user == owner_id)
    try:
        provider_id = identificator if isinstance(identificator, UUID) else UUID(identificator)
        stmt = select(AiProvider).where(AiProvider.id == provider_id, visibility)
    except ValueError:
        stmt = select(AiProvider).where(AiProvider.slug == identificator, visibility)
    if not include_inactive:
        stmt = stmt.where(AiProvider.is_active.is_(True))
    provider = db.scalar(stmt)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider não encontrado")
        
    return provider

def list_providers(db: Session, filters: dict | None) -> list[AiProvider]:
    stmt = select(AiProvider).where(
        AiProvider.id_user.is_(None), AiProvider.is_active.is_(True)
    )
    for k, v in (filters or {}).items():
        if not hasattr(AiProvider, k):
            raise HTTPException(status_code=400, detail=f"Invalid filter: {k}")
        collum_attr = getattr(AiProvider, k)
        stmt = stmt.where(collum_attr == v)
    
    providers = db.scalars(stmt).all()
    
    return providers

def create_provider(provider_data: ProviderCreate, db: Session) -> AiProvider:
    new_provider = AiProvider(
        id=uuid4(),
        slug=provider_data.slug,
        display_name=provider_data.display_name,
        base_url=provider_data.base_url,
        protocol=provider_data.protocol,
        is_active=True,
        created_at=datetime.now()
    )
    
    db.add(new_provider)
    db.commit()
    db.refresh(new_provider)
    return new_provider

def update_provider(identificator : str, provider_data: ProviderUpdate, db: Session) -> AiProvider:
    provider = get_provider(identificator, db, include_inactive=True)
    
    for k, v in provider_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(provider, k, v)
    provider.updated_at = datetime.now()
    db.commit()
    db.refresh(provider)
    return provider

def delete_provider(identificator : str, db: Session) -> bool:
    provider = get_provider(identificator, db)
    provider.is_active = False
    provider.updated_at = datetime.now()
    db.commit()
    return True


################
### AI Model
################
def get_ai_model(
    identificator: UUID | str,
    db: Session,
    owner_id: UUID | None = None,
    include_inactive: bool = False,
) -> AiModel:
    visibility = AiProvider.id_user.is_(None)
    if owner_id is not None:
        visibility = or_(visibility, AiProvider.id_user == owner_id)
    try:
        model_id = identificator if isinstance(identificator, UUID) else UUID(identificator)
        stmt = (
            select(AiModel)
            .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
            .where(AiModel.id == model_id, visibility)
        )
    except ValueError:
        stmt = (
            select(AiModel)
            .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
            .where(AiModel.slug == identificator, visibility)
        )
    if not include_inactive:
        stmt = stmt.where(
            AiModel.is_active.is_(True), AiProvider.is_active.is_(True)
        )
    ai_model = db.scalar(stmt)
    if ai_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modelo de Ia não encontrado")
        
    return ai_model

def list_ai_models(db: Session, filters: dict | None) -> list[AiModel]:
    stmt = (
        select(AiModel)
        .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
        .where(
            AiProvider.id_user.is_(None),
            AiProvider.is_active.is_(True),
            AiModel.is_active.is_(True),
        )
    )
    for k, v in (filters or {}).items():
        if not hasattr(AiModel, k):
            raise HTTPException(status_code=400, detail=f"Invalid filter: {k}")
        collum_attr = getattr(AiModel, k)
        stmt = stmt.where(collum_attr == v)
    
    ai_models = db.scalars(stmt).all()
    
    return ai_models

def create_ai_model(ai_model_data: AiModelCreate, db: Session) -> AiModel:
    get_provider(ai_model_data.id_ai_provider, db)
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
    ai_model = get_ai_model(identificator, db, include_inactive=True)

    changes = provider_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    if "id_ai_provider" in changes:
        get_provider(changes["id_ai_provider"], db, include_inactive=True)
    for k, v in changes.items():
        setattr(ai_model, k, v)
    ai_model.updated_at = datetime.now()
    db.commit()
    db.refresh(ai_model)
    return ai_model

def delete_ai_model(identificator : str, db: Session) -> bool:
    ai_model = get_ai_model(identificator, db)
    ai_model.is_active = False
    ai_model.updated_at = datetime.now()
    db.commit()
    return True


################
### User API Key
################

def get_user_api_key(token: str, identificator: UUID | str, db: Session) -> UserApiKey:
    user = get_current_user(token, db)
    try:
        key_id = identificator if isinstance(identificator, UUID) else UUID(identificator)
        user_api_key = db.scalar(
            select(UserApiKey).where(
                and_(UserApiKey.id_user == user.id, UserApiKey.id == key_id)
            )
        )
    except ValueError:
        user_api_key = None
        
    if user_api_key is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Api Key não encontrada")
     
    return user_api_key

def list_user_api_keys(token: str, filters: dict | None, db: Session) -> list[UserApiKey]:
    user = get_current_user(token, db)
    stmt = select(UserApiKey).where(UserApiKey.id_user == user.id)
    
    for k, v in (filters or {}).items():
        if not hasattr(UserApiKey, k):
            raise HTTPException(status_code=400, detail=f"Invalid filter: {k}")
        attr = getattr(UserApiKey, k)
        stmt = stmt.where(attr == v)
        
    user_api_keys = db.scalars(stmt).all()
    
    return user_api_keys

def create_user_api_key(token: str, create_data: UserApiKeyCreate, db: Session) -> UserApiKey:
    user = get_current_user(token, db)
    provider = db.scalar(
        select(AiProvider).where(
            AiProvider.id == create_data.id_ai_provider,
            or_(AiProvider.id_user.is_(None), AiProvider.id_user == user.id),
            AiProvider.is_active.is_(True),
        )
    )
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider não encontrado",
        )
    if provider.protocol != "openai_compatible" and not create_data.api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An API key is required for this provider.",
        )
    new_api_key = UserApiKey(
        id=uuid4(),
        id_ai_provider=create_data.id_ai_provider,
        id_user=user.id,
        name=create_data.name,
        encrypted_key=encrypt(create_data.api_key),
        is_active=create_data.is_active,
        created_at=datetime.now()
    )
    
    db.add(new_api_key)
    db.commit()
    db.refresh(new_api_key)
    return new_api_key

def update_user_api_key(token: str, identificator: str, upd_data: UserApiKeyUpdate, db: Session) -> UserApiKey:
    upd_api_key = get_user_api_key(token, identificator, db)
    user = get_current_user(token, db)
    changes = upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True)
    provider_id = changes.get("id_ai_provider", upd_api_key.id_ai_provider)
    provider = db.scalar(
        select(AiProvider).where(
            AiProvider.id == provider_id,
            or_(AiProvider.id_user.is_(None), AiProvider.id_user == user.id),
            AiProvider.is_active.is_(True),
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider não encontrado")
    existing_key = (
        changes["api_key"]
        if "api_key" in changes
        else decrypt(upd_api_key.encrypted_key)
    )
    if provider.protocol != "openai_compatible" and not existing_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An API key is required for this provider.",
        )

    for k, v in changes.items():
        if k == "id_user":
            continue
        if k == "api_key":
            upd_api_key.encrypted_key = encrypt(v)
        else:
            setattr(upd_api_key, k, v)    
    
    upd_api_key.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_api_key)
    return upd_api_key

def delete_user_api_key(token: str, identificator: str, db: Session) -> bool:
    del_api_key = get_user_api_key(token, identificator, db)
    del_api_key.is_active = False
    del_api_key.updated_at = datetime.now()
    db.commit()
    return True

################
### Ai Agent
################
def get_agent(
    identificator: str, db: Session, include_inactive: bool = False
) -> Agent:

    stmt = select(Agent).where(
        Agent.id == UUID(identificator),
        Agent.id_user.is_(None),
    )
    if not include_inactive:
        stmt = stmt.where(Agent.is_active.is_(True))
    agent = db.scalar(stmt)
        
    if agent is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agente não encontrado")
     
    return agent

def list_agents(filters: AgentFilters | None, db: Session) -> list[Agent]:
    stmt = select(Agent).where(
        Agent.id_user.is_(None), Agent.is_active.is_(True)
    )
    
    for k, v in (filters or {}).items():
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
    upd_agent = get_agent(identificator, db, include_inactive=True)
    
    for k, v in upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True).items():
        setattr(upd_agent, k, v)    
    
    upd_agent.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_agent)
    return upd_agent

def delete_agent(identificator: str, db: Session) -> bool:
    del_agent = get_agent(identificator, db)
    del_agent.is_active = False
    del_agent.updated_at = datetime.now()
    db.commit()
    return True


################
### Agent Model
################
def get_agent_model(
    identificator: str, db: Session, include_inactive: bool = False
) -> AgentModel:

    stmt = (
        select(AgentModel)
        .join(Agent, Agent.id == AgentModel.id_agent)
        .where(AgentModel.id == UUID(identificator), Agent.id_user.is_(None))
    )
    if not include_inactive:
        stmt = stmt.where(
            Agent.is_active.is_(True), AgentModel.is_active.is_(True)
        )
    agent_model = db.scalar(stmt)

    if agent_model is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agente_Modelo de Ia não encontrado")
     
    return agent_model

def list_agent_models(
    filters: AgentModelFilters | None,
    db: Session,
    owner_id: UUID | None = None,
) -> list[AgentModel]:
    visibility = Agent.id_user.is_(None)
    if owner_id is not None:
        visibility = or_(visibility, Agent.id_user == owner_id)
    stmt = (
        select(AgentModel)
        .join(Agent, Agent.id == AgentModel.id_agent)
        .join(AiModel, AiModel.id == AgentModel.id_ai_model)
        .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
        .where(
            visibility,
            Agent.is_active.is_(True),
            AgentModel.is_active.is_(True),
            AiModel.is_active.is_(True),
            AiProvider.is_active.is_(True),
            or_(AiProvider.id_user.is_(None), AiProvider.id_user == owner_id)
            if owner_id is not None
            else AiProvider.id_user.is_(None),
        )
    )

    if isinstance(filters, dict):
        filters_data = filters
    else:
        filters_data = filters.model_dump(exclude_none=True) if filters else {}

    for k, v in filters_data.items():
        attr = getattr(AgentModel, k)
        stmt = stmt.where(attr == v)

    agent_models = db.scalars(stmt).all()
    return agent_models

def create_agent_model(create_data: AgentModelCreate, db: Session) -> AgentModel:
    get_agent(str(create_data.id_agent), db)
    get_ai_model(create_data.id_ai_model, db)
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
    upd_agent_model = get_agent_model(identificator, db, include_inactive=True)
    changes = upd_data.model_dump(exclude_defaults=True, exclude_none=True, exclude_unset=True)
    if "id_agent" in changes:
        get_agent(str(changes["id_agent"]), db)
    if "id_ai_model" in changes:
        get_ai_model(changes["id_ai_model"], db, include_inactive=True)
    for k, v in changes.items():
        setattr(upd_agent_model, k, v)    
    
    upd_agent_model.updated_at = datetime.now() 
    
    db.commit()
    db.refresh(upd_agent_model)
    return upd_agent_model

def delete_agent_model(identificator: str, db: Session) -> bool:
    del_agent_model = get_agent_model(identificator, db)
    del_agent_model.is_active = False
    del_agent_model.updated_at = datetime.now()
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
            UserApiKey.id_user == user.id,
            or_(
                UserApiKeyCanUseIaModel.id == UUID(identificator),
                UserApiKeyCanUseIaModel.id_ai_model == UUID(identificator),
            ),
        )
    )

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
    if not obj_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An inactive API key cannot be linked to a model.",
        )
    
    obj_ai_model = get_ai_model(create_data.id_ai_model, db, owner_id=user.id)
    
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
        .where(
            AiUsageLog.id == UUID(identificator),
            AiUsageLog.id_user == user.id
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
        usage_details=create_data.usage_details,
        created_at=datetime.now()
    )    
    
    db.add(new_ai_usage_log)
    db.commit()
    db.refresh(new_ai_usage_log)
    return new_ai_usage_log