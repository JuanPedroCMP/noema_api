import pytest
from pydantic import ValidationError

from app.modules.ai_provider.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphType,
    ManipulateGraphResponse,
    ManipulateNodeResponse,
)
from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider


def test_graph_creation_contract_adds_optional_defaults_without_breaking_legacy():
    response = ManipulateGraphResponse.model_validate(
        {
            "graph_title": "Aprendizado supervisionado",
            "nodes": [
                {"node_id": 1, "title": "Regressão", "type": "CONCEPT"},
            ],
            "edges": [
                {"source_node": 1, "target_node": 1, "type": "PREREQUISITE"},
            ],
        }
    )

    assert response.plan == ""
    assert response.nodes[0].level == "core"
    assert response.edges[0].weight == 1.0
    assert AiProvider._get_response_model("manipulate_graph") is ManipulateGraphResponse
    assert AiProvider._get_response_model("manipulate_node") is ManipulateNodeResponse
    schema = ManipulateGraphResponse.model_json_schema()
    assert list(schema["properties"])[0] == "plan"
    assert "not persisted" in schema["$defs"]["GraphNode"]["properties"]["level"][
        "description"
    ]
    assert (
        "containment"
        in schema["$defs"]["GraphEdge"]["properties"]["type"]["description"]
    )


def test_graph_creation_contract_validates_level_and_edge_weight():
    assert GraphNode(
        node_id=1,
        title="Fundamentos",
        type=GraphType.CONCEPT,
        level="foundation",
    ).level == "foundation"
    assert GraphEdge(
        source_node=1,
        target_node=2,
        type=EdgeType.PREREQUISITE,
        weight=0.5,
    ).weight == 0.5

    with pytest.raises(ValidationError):
        GraphNode(
            node_id=1,
            title="Invalido",
            type=GraphType.CONCEPT,
            level="beginner",
        )
    with pytest.raises(ValidationError):
        GraphEdge(
            source_node=1,
            target_node=2,
            type=EdgeType.PREREQUISITE,
            weight=1.1,
        )
