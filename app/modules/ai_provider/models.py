from pydantic import BaseModel, Json
from uuid import UUID

class AiResponse(BaseModel):
    id_agent: UUID
    id_model:UUID
    id_ai_api_key: UUID
    response: Json