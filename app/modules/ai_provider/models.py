from pydantic import BaseModel, Json
from uuid import UUID

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
    node_title: str
    node_description:str
class GraphEdge(BaseModel):
    source_node: int
    target_node: int
    edge_type:str

