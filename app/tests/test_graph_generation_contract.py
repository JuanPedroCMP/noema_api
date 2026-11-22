import pytest
from pydantic import ValidationError

from app.modules.ai_provider.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphType,
    ManipulateGraphPatchResponse,
    ManipulateGraphPlanResponse,
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
    assert response.coverage == []
    assert response.nodes[0].level == "core"
    assert response.nodes[0].description == ""
    assert response.edges[0].weight == 1.0
    assert AiProvider._get_response_model("manipulate_graph") is ManipulateGraphResponse
    assert AiProvider._get_response_model("manipulate_node") is ManipulateNodeResponse
    schema = ManipulateGraphResponse.model_json_schema()
    assert list(schema["properties"])[0] == "plan"
    assert "coverage ledger" in schema["properties"]["coverage"]["description"].lower()
    assert "not persisted" in schema["$defs"]["GraphNode"]["properties"]["level"][
        "description"
    ]
    assert "learning objective" in schema["$defs"]["GraphNode"]["properties"][
        "description"
    ]["description"]
    assert (
        "containment"
        in schema["$defs"]["GraphEdge"]["properties"]["type"]["description"]
    )


def test_graph_coverage_ledger_maps_outcomes_to_leaf_ids():
    response = ManipulateGraphResponse.model_validate(
        {
            "graph_title": "Equações",
            "plan": "Resolver equações de primeiro grau.",
            "coverage": [
                {
                    "outcome": "Resolver operações inversas.",
                    "node_ids": [1, 2],
                }
            ],
            "nodes": [],
            "edges": [],
        }
    )

    assert response.coverage[0].node_ids == [1, 2]
    with pytest.raises(ValidationError):
        ManipulateGraphResponse.model_validate(
            {
                "graph_title": "Equações",
                "coverage": [
                    {"outcome": "Resolver equações.", "node_ids": [True]}
                ],
                "nodes": [],
                "edges": [],
            }
        )


def test_graph_creation_contract_validates_level_and_edge_weight():
    assert GraphNode(
        node_id=1,
        title="Fundamentos",
        description="Resolver operações com números reais.",
        type=GraphType.CONCEPT,
        level="foundation",
    ).description == "Resolver operações com números reais."
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
            "MODE: PLAN\nPlan a study graph.",
        )
        is ManipulateGraphPlanResponse
    )
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
    mode_instruction = AiProvider._apply_response_mode_instruction(
        "Legacy graph prompt.",
        ManipulateGraphPlanResponse,
    )
    assert "overrides any generic edit fallback" in mode_instruction
    assert "Do not return graph nodes, edges" in mode_instruction
    assert (
        AiProvider._get_response_model_for_prompt(
            ManipulateGraphResponse,
            "Apply this graph change.",
        )
        is ManipulateGraphPatchResponse
    )


def test_graph_blueprint_contract_rejects_broken_outcome_dependencies():
    blueprint = {
        "scope": "Train and evaluate a simple model.",
        "outcomes": [
            {
                "id": "outcome_1",
                "outcome": "Prepare input data.",
                "evidence": "Transform a small dataset into model inputs.",
                "prerequisite_ids": ["outcome_2"],
            },
            {
                "id": "outcome_2",
                "outcome": "Evaluate model output.",
                "evidence": "Interpret predictions against a baseline.",
                "prerequisite_ids": ["outcome_1"],
            },
        ],
    }

    valid_blueprint = ManipulateGraphPlanResponse.model_validate(
        {
            "scope": blueprint["scope"],
            "assumptions": [],
            "prior_knowledge": [],
            "outcomes": [
                {
                    "id": "outcome_1",
                    "outcome": "Prepare input data.",
                    "evidence": "Transform a small dataset into model inputs.",
                    "prerequisite_ids": [],
                },
                {
                    "id": "outcome_2",
                    "outcome": "Evaluate model output.",
                    "evidence": "Interpret predictions against a baseline.",
                    "prerequisite_ids": ["outcome_1"],
                },
            ],
        }
    )
    assert valid_blueprint.outcomes[1].prerequisite_ids == ["outcome_1"]

    with pytest.raises(ValidationError, match="contain a cycle"):
        ManipulateGraphPlanResponse.model_validate(blueprint)

    blueprint["outcomes"][1]["prerequisite_ids"] = ["outcome_missing"]
    with pytest.raises(ValidationError, match="unknown prerequisite"):
        ManipulateGraphPlanResponse.model_validate(blueprint)


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
