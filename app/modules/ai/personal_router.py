from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...core.ai_endpoint import validate_ai_endpoint
from ...core.database import get_db
from ...core.db_models.ai_models import (
    Agent,
    AgentModel,
    AgentModelQuality,
    AiModel,
    AiProvider,
    TaskType,
)
from ...core.db_models.app_auth_models import User
from ...core.security import get_current_user, oauth2_scheme
from .models import AgentModelOut, AgentOut, AiModelOut, ProviderOut

router = APIRouter(prefix="/ai/me", tags=["Personal AI configuration"])


def current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return get_current_user(token, db)


def _owned_provider(db: Session, user_id: UUID, provider_id: UUID) -> AiProvider:
    provider = db.scalar(
        select(AiProvider).where(
            AiProvider.id == provider_id,
            AiProvider.id_user == user_id,
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found.")
    return provider


def _visible_provider(db: Session, user_id: UUID, provider_id: UUID) -> AiProvider:
    provider = db.scalar(
        select(AiProvider).where(
            AiProvider.id == provider_id,
            or_(AiProvider.id_user.is_(None), AiProvider.id_user == user_id),
            AiProvider.is_active.is_(True),
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found.")
    return provider


def _owned_model(db: Session, user_id: UUID, model_id: UUID) -> AiModel:
    model = db.scalar(
        select(AiModel)
        .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
        .where(AiModel.id == model_id, AiProvider.id_user == user_id)
    )
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    return model


def _visible_model(db: Session, user_id: UUID, model_id: UUID) -> AiModel:
    model = db.scalar(
        select(AiModel)
        .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
        .where(
            AiModel.id == model_id,
            or_(AiProvider.id_user.is_(None), AiProvider.id_user == user_id),
            AiModel.is_active.is_(True),
            AiProvider.is_active.is_(True),
        )
    )
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    return model


def _owned_agent(db: Session, user_id: UUID, agent_id: UUID) -> Agent:
    agent = db.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.id_user == user_id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


class PersonalProviderCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    base_url: AnyHttpUrl
    protocol: Literal["openai_compatible"] = "openai_compatible"


class PersonalProviderUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: AnyHttpUrl | None = None
    is_active: bool | None = None


class PersonalModelCreate(BaseModel):
    id_ai_provider: UUID
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    context_window: int = Field(gt=0)
    input_token_limit: int = Field(gt=0)
    output_token_limit: int = Field(gt=0)
    supports_vision: bool = False


class PersonalModelUpdate(BaseModel):
    id_ai_provider: UUID | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    context_window: int | None = Field(default=None, gt=0)
    input_token_limit: int | None = Field(default=None, gt=0)
    output_token_limit: int | None = Field(default=None, gt=0)
    supports_vision: bool | None = None
    is_active: bool | None = None


class PersonalAgentCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=64)
    task: TaskType
    base_system_prompt: str = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)


class PersonalAgentUpdate(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=64)
    task: TaskType | None = None
    base_system_prompt: str | None = Field(default=None, min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    is_active: bool | None = None


class PersonalAgentModelCreate(BaseModel):
    id_agent: UUID
    id_ai_model: UUID
    quality_expected: AgentModelQuality
    custom_system_prompt: str = ""
    temperature: float | None = Field(default=None, ge=0, le=2)


class PersonalAgentModelUpdate(BaseModel):
    id_ai_model: UUID | None = None
    quality_expected: AgentModelQuality | None = None
    custom_system_prompt: str | None = None
    custom_temperature: float | None = Field(default=None, ge=0, le=2)
    is_active: bool | None = None


@router.get("/providers", response_model=list[ProviderOut])
def list_personal_providers(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[AiProvider]:
    return list(
        db.scalars(
            select(AiProvider).where(
                or_(AiProvider.id_user.is_(None), AiProvider.id_user == user.id),
                AiProvider.is_active.is_(True),
            )
        ).all()
    )


@router.get("/providers/{provider_id}", response_model=ProviderOut)
def get_personal_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiProvider:
    return _visible_provider(db, user.id, provider_id)


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_personal_provider(
    data: PersonalProviderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiProvider:
    base_url = str(data.base_url).rstrip("/")
    validate_ai_endpoint(base_url)
    provider = AiProvider(
        id=uuid4(),
        id_user=user.id,
        slug=data.slug,
        display_name=data.display_name,
        base_url=base_url,
        protocol=data.protocol,
        is_active=True,
        created_at=datetime.now(),
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@router.put("/providers/{provider_id}", response_model=ProviderOut)
def update_personal_provider(
    provider_id: UUID,
    data: PersonalProviderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiProvider:
    provider = _owned_provider(db, user.id, provider_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "base_url" in changes and changes["base_url"] is not None:
        changes["base_url"] = str(changes["base_url"]).rstrip("/")
        validate_ai_endpoint(changes["base_url"])
    for field, value in changes.items():
        setattr(provider, field, value)
    provider.updated_at = datetime.now()
    db.commit()
    db.refresh(provider)
    return provider


@router.delete("/providers/{provider_id}", status_code=204)
def delete_personal_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    provider = _owned_provider(db, user.id, provider_id)
    provider.is_active = False
    provider.updated_at = datetime.now()
    db.commit()


@router.get("/models", response_model=list[AiModelOut])
def list_personal_models(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[AiModel]:
    return list(
        db.scalars(
            select(AiModel)
            .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
            .where(
                or_(AiProvider.id_user.is_(None), AiProvider.id_user == user.id),
                AiProvider.is_active.is_(True),
                AiModel.is_active.is_(True),
            )
        ).all()
    )


@router.post("/models", response_model=AiModelOut, status_code=201)
def create_personal_model(
    data: PersonalModelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiModel:
    provider = _owned_provider(db, user.id, data.id_ai_provider)
    if not provider.is_active:
        raise HTTPException(status_code=404, detail="Provider not found.")
    model = AiModel(
        id=uuid4(),
        id_ai_provider=data.id_ai_provider,
        slug=data.slug,
        display_name=data.display_name,
        context_window=data.context_window,
        input_token_limit=data.input_token_limit,
        output_token_limit=data.output_token_limit,
        supports_vision=data.supports_vision,
        is_active=True,
        created_at=datetime.now(),
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.get("/models/{model_id}", response_model=AiModelOut)
def get_personal_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiModel:
    return _visible_model(db, user.id, model_id)


@router.put("/models/{model_id}", response_model=AiModelOut)
def update_personal_model(
    model_id: UUID,
    data: PersonalModelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AiModel:
    model = _owned_model(db, user.id, model_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "id_ai_provider" in changes and changes["id_ai_provider"] is not None:
        provider = _owned_provider(db, user.id, changes["id_ai_provider"])
        if not provider.is_active:
            raise HTTPException(status_code=404, detail="Provider not found.")
    elif changes.get("is_active") is True:
        provider = _owned_provider(db, user.id, model.id_ai_provider)
        if not provider.is_active:
            raise HTTPException(status_code=404, detail="Provider not found.")
    for field, value in changes.items():
        setattr(model, field, value)
    model.updated_at = datetime.now()
    db.commit()
    db.refresh(model)
    return model


@router.delete("/models/{model_id}", status_code=204)
def delete_personal_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    model = _owned_model(db, user.id, model_id)
    model.is_active = False
    model.updated_at = datetime.now()
    db.commit()


@router.get("/agents", response_model=list[AgentOut])
def list_personal_agents(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[Agent]:
    return list(
        db.scalars(
            select(Agent).where(
                or_(Agent.id_user.is_(None), Agent.id_user == user.id),
                Agent.is_active.is_(True),
            )
        ).all()
    )


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_personal_agent(
    data: PersonalAgentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Agent:
    agent = Agent(id=uuid4(), id_user=user.id, **data.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_personal_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Agent:
    agent = db.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            or_(Agent.id_user.is_(None), Agent.id_user == user.id),
            Agent.is_active.is_(True),
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@router.put("/agents/{agent_id}", response_model=AgentOut)
def update_personal_agent(
    agent_id: UUID,
    data: PersonalAgentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Agent:
    agent = _owned_agent(db, user.id, agent_id)
    for field, value in data.model_dump(
        exclude_unset=True, exclude_none=True
    ).items():
        setattr(agent, field, value)
    agent.updated_at = datetime.now()
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}", status_code=204)
def delete_personal_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    agent = _owned_agent(db, user.id, agent_id)
    agent.is_active = False
    agent.updated_at = datetime.now()
    db.commit()


@router.get("/agent-models", response_model=list[AgentModelOut])
def list_personal_agent_models(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[AgentModel]:
    return list(
        db.scalars(
            select(AgentModel)
            .join(Agent, Agent.id == AgentModel.id_agent)
            .join(AiModel, AiModel.id == AgentModel.id_ai_model)
            .join(AiProvider, AiProvider.id == AiModel.id_ai_provider)
            .where(
                Agent.id_user == user.id,
                Agent.is_active.is_(True),
                AgentModel.is_active.is_(True),
                AiModel.is_active.is_(True),
                AiProvider.is_active.is_(True),
            )
        ).all()
    )


@router.post("/agent-models", response_model=AgentModelOut, status_code=201)
def create_personal_agent_model(
    data: PersonalAgentModelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AgentModel:
    _owned_agent(db, user.id, data.id_agent)
    _visible_model(db, user.id, data.id_ai_model)
    model_link = AgentModel(
        id=uuid4(),
        id_agent=data.id_agent,
        id_ai_model=data.id_ai_model,
        quality_expected=data.quality_expected,
        custom_system_prompt=data.custom_system_prompt,
        custom_temperature=data.temperature,
        created_at=datetime.now(),
    )
    db.add(model_link)
    db.commit()
    db.refresh(model_link)
    return model_link


@router.get("/agent-models/{link_id}", response_model=AgentModelOut)
def get_personal_agent_model(
    link_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AgentModel:
    model_link = db.scalar(
        select(AgentModel)
        .join(Agent, Agent.id == AgentModel.id_agent)
        .where(
            AgentModel.id == link_id,
            or_(Agent.id_user.is_(None), Agent.id_user == user.id),
            Agent.is_active.is_(True),
            AgentModel.is_active.is_(True),
        )
    )
    if model_link is None:
        raise HTTPException(status_code=404, detail="Agent-model link not found.")
    return model_link


@router.put("/agent-models/{link_id}", response_model=AgentModelOut)
def update_personal_agent_model(
    link_id: UUID,
    data: PersonalAgentModelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AgentModel:
    model_link = db.scalar(
        select(AgentModel)
        .join(Agent, Agent.id == AgentModel.id_agent)
        .where(AgentModel.id == link_id, Agent.id_user == user.id)
    )
    if model_link is None:
        raise HTTPException(status_code=404, detail="Agent-model link not found.")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "id_ai_model" in changes and changes["id_ai_model"] is not None:
        _visible_model(db, user.id, changes["id_ai_model"])
    elif changes.get("is_active") is True:
        _visible_model(db, user.id, model_link.id_ai_model)
    for field, value in changes.items():
        setattr(
            model_link,
            field,
            value,
        )
    model_link.updated_at = datetime.now()
    db.commit()
    db.refresh(model_link)
    return model_link


@router.delete("/agent-models/{link_id}", status_code=204)
def delete_personal_agent_model(
    link_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    model_link = db.scalar(
        select(AgentModel)
        .join(Agent, Agent.id == AgentModel.id_agent)
        .where(AgentModel.id == link_id, Agent.id_user == user.id)
    )
    if model_link is None:
        raise HTTPException(status_code=404, detail="Agent-model link not found.")
    model_link.is_active = False
    model_link.updated_at = datetime.now()
    db.commit()
