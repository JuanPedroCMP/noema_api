from pydantic import BaseModel, Json
from uuid import UUID
from enum import Enum

class GraphType(Enum):
    AREA = "AREA"
    TOPIC = "TOPIC"
    CONCEPT = "CONCEPT"
    SUBCONCEPT = "SUBCONCEPT"
    
class EdgeType(Enum):
    SUBTOPIC = "SUBTOPIC"
    PREREQUISITE = "PREREQUISITE"

class AiResponseOut(BaseModel):
    id_agent: UUID
    id_model:UUID
    id_ai_api_key: UUID
    response: Json
    
class AiGraphResponse(BaseModel):
    graph_title: str
    graph_description:str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    
class GraphNode(BaseModel):
    node_id: int
    title: str
    description:str
    type: GraphType
class GraphEdge(BaseModel):
    source_node: int
    target_node: int
    type: EdgeType

