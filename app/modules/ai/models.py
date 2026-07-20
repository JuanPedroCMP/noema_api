from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict, Json
from ...core.db_models.ai_models import TaskType, AgentModelQuality

################
### Provider
################
class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    slug: str
    display_name: str
    base_url: str
    is_active: bool | None
    created_at: datetime | None
    updated_at: datetime| None
    
class ProviderFilters(BaseModel):
    id: Optional[UUID | None] = None
    slug: Optional[str | None] = None
    display_name: Optional[str | None] = None
    base_url: Optional[str | None ]= None
    is_active: Optional[bool | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class ProviderCreate(BaseModel):
    slug: str
    display_name: str
    base_url: str

class ProviderUpdate(BaseModel):
    slug: Optional[str | None] = None
    display_name: Optional[str | None] = None
    base_url: Optional[str | None ]= None
    is_active: Optional[bool | None] = None

################    
### AI Model
################
class AiModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_ai_provider: UUID
    slug: str
    display_name: str
    context_window: int
    input_token_limit: int
    output_token_limit: int
    supports_vision: bool | None
    is_active: bool | None
    created_at: datetime | None
    updated_at: datetime| None
    
class AiModelCreate(BaseModel):
    slug: str
    id_ai_provider: UUID
    display_name: str
    context_window: int
    input_token_limit: int
    output_token_limit: int
    supports_vision: bool | None
    is_active: bool | None

class AiModelUpdate(BaseModel):
    slug: Optional[str | None] = None
    id_ai_provider: Optional[UUID | None] = None
    display_name: Optional[str | None] = None
    context_window: Optional[int | None] = None
    input_token_limit: Optional[int | None] = None
    output_token_limit:Optional[ int | None] = None
    supports_vision: Optional[bool | None] = None
    is_active: Optional[bool | None] = None
    
class AiModelFilters(BaseModel):
    id: Optional[UUID | None] = None
    slug: Optional[str | None] = None
    id_ai_provider: Optional[UUID | None] = None
    display_name: Optional[str | None] = None
    context_window: Optional[int | None] = None
    input_token_limit: Optional[int | None] = None
    output_token_limit:Optional[ int | None] = None
    supports_vision: Optional[bool | None] = None
    is_active: Optional[bool | None] = None

################
### User API Key
################
class UserApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_ai_provider: UUID
    id_user: UUID
    name: str
    encrypted_key: str
    is_active: bool
    created_at: datetime | None
    updated_at: datetime| None
    
class UserApiKeyCreate(BaseModel):
    id_ai_provider: UUID
    name: str
    api_key: str
    is_active: bool = True
    
class UserApiKeyUpdate(BaseModel):
    id_ai_provider: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    api_key: Optional[str | None] = None
    is_active: Optional[bool | None] = None
    
class UserApiKeyFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_ai_provider: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    encrypted_key: Optional[str | None] = None
    is_active: Optional[bool | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime | None] = None

################
### Agent
################
class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    alias: str
    task: TaskType
    base_system_prompt: str
    temperature: Optional[float | None]
    created_at: datetime | None
    updated_at: datetime| None
    
class AgentCreate(BaseModel):
    alias: str
    task: TaskType
    base_system_prompt: str
    temperature: Optional[float | None]

class AgentUpdate(BaseModel):
    alias: Optional[str | None] = None
    task: Optional[TaskType | None] = None
    base_system_prompt: Optional[str | None] = None
    temperature: Optional[float | None] = None
    
class AgentFilters(BaseModel):
    id: Optional[UUID  | None] = None
    alias: Optional[str | None] = None
    task: Optional[TaskType | None] = None
    base_system_prompt: Optional[str | None] = None
    temperature: Optional[float | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
################
### AgentModel
################
class AgentModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_agent: UUID
    id_ai_model: UUID
    quality_expected: AgentModelQuality
    custom_system_prompt: str
    custom_temperature: Optional[float | None]
    created_at: datetime | None
    updated_at: datetime| None
    
class AgentModelCreate(BaseModel):
    id_agent: UUID
    id_ai_model: UUID
    quality_expected: AgentModelQuality
    custom_system_prompt: str
    temperature: Optional[float | None]

class AgentModelUpdate(BaseModel):
    id_agent: Optional[UUID | None] = None
    id_ai_model: Optional[UUID | None] = None
    quality_expected: Optional[AgentModelQuality | None] = None
    custom_system_prompt: Optional[str | None] = None
    custom_temperature: Optional[float | None] = None
    
class AgentModelFilters(BaseModel):
    id: Optional[UUID  | None] = None
    id_agent: Optional[UUID | None] = None
    id_ai_model: Optional[UUID | None] = None
    quality_expected: Optional[AgentModelQuality | None] = None
    custom_system_prompt: Optional[str | None] = None
    custom_temperature: Optional[float | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None

################
### UserApiKeyCanUseIaModel
################
class UserApiKeyCanUseIaModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_ai_model: UUID
    id_user_api_key: UUID
    created_at: datetime | None

class UserApiKeyCanUseIaModelCreate(BaseModel):
    id_ai_model: UUID
    id_user_api_key: UUID

    
class UserApiKeyCanUseIaModelFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_ai_model: Optional[UUID | None] = None
    id_user_api_key: Optional[UUID | None] = None
    created_at: Optional[datetime | None] = None
    
################
### AiUsageLog
################
class AiUsageLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_user: UUID
    id_agent_model: UUID
    usage_datails: Json
    created_at: datetime | None

class AiUsageLogCreate(BaseModel):
    id_user: UUID
    id_agent_model: UUID
    usage_datails: Json

    
class AiUsageLogFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    id_agent_model: Optional[UUID | None] = None
    usage_datails: Optional[Json | None] = None
    created_at: Optional[datetime | None] = None

