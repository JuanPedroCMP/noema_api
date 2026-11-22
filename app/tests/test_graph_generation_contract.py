import pytest
from pydantic import ValidationError

from app.modules.ai_provider.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphType,
    ManipulateGraphPatchResponse,
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


def test_graph_task_selects_full_graph_for_create_and_patch_for_edit():
    assert (
        AiProvider._get_response_model_for_prompt(
            ManipulateGraphResponse,
            "MODE: CREATE\nCreate a learning graph.",
        )
        is ManipulateGraphResponse
    )
    assert (
        AiProvider._get_response_model_for_prompt(
            ManipulateGraphResponse,
            "MODE: EDIT\nAdd a concept.",
        )
        is ManipulateGraphPatchResponse
    )
    assert (
        AiProvider._get_response_model_for_prompt(
            ManipulateGraphResponse,
            "Apply this graph change.",
        )
        is ManipulateGraphPatchResponse
    )


def test_graph_edit_patch_contract_matches_the_app_payload():
    patch = ManipulateGraphPatchResponse.model_validate(
        {
            "delete_nodes": [1],
            "rename_nodes": [{"id": 2, "title": "Renamed"}],
            "add_nodes": [{"id": "new_1", "title": "New concept"}],
            "delete_edges": [3],
            "add_edges": [
                {
                    "source_node": 2,
                    "target_node": "new_1",
                    "type": "PREREQUISITE",
                    "weight": 0.5,
                }
            ],
        }
    )

    assert patch.model_dump(mode="json") == {
        "delete_nodes": [1],
        "rename_nodes": [{"id": 2, "title": "Renamed"}],
        "add_nodes": [
            {"id": "new_1", "title": "New concept", "type": "CONCEPT"}
        ],
        "delete_edges": [3],
        "add_edges": [
            {
                "source_node": 2,
                "target_node": "new_1",
                "type": "PREREQUISITE",
                "weight": 0.5,
            }
        ],
    }

    with pytest.raises(ValidationError):
        ManipulateGraphPatchResponse.model_validate(
            {
                "add_nodes": [{"id": "temporary", "title": "Invalid"}],
            }
        )
