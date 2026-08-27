from pydantic import BaseModel, Json
from uuid import UUID
from enum import Enum
class AiResponseOut(BaseModel):
    id_agent: UUID
    id_model:UUID
    id_ai_api_key: UUID
    response: Json
    
###################
### Graph Generation
###################
class GraphType(Enum):
    AREA = "AREA"
    TOPIC = "TOPIC"
    CONCEPT = "CONCEPT"
    SUBCONCEPT = "SUBCONCEPT"
    
class EdgeType(Enum):
    SUBTOPIC = "SUBTOPIC"
    PREREQUISITE = "PREREQUISITE"

class ManipulateGraphResponse(BaseModel):
    graph_title: str
  # graph_description:str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    
class GraphNode(BaseModel):
    node_id: int
    title: str
  # description:str
    type: GraphType
class GraphEdge(BaseModel):
    source_node: int
    target_node: int
    type: EdgeType
    
###################
### External resources query generation
###################
class Queries(BaseModel):
    paper_query: str
    search_query: str
    yt_videos_query: str
    books_query: str

