import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.ai_provider import router as ai_router
from app.modules.ai_provider.models import (
    EdgeType,
    GraphBlueprintOutcome,
    GraphCoverageItem,
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
    assert "Make each outcome atomic" in mode_instruction
    create_instruction = AiProvider._apply_response_mode_instruction(
        "Legacy graph prompt.",
        ManipulateGraphResponse,
    )
    assert "whole subject, chapter" in create_instruction
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


def _pipeline_blueprint() -> ManipulateGraphPlanResponse:
    return ManipulateGraphPlanResponse(
        scope="Prepare inputs and evaluate model predictions.",
        outcomes=[
            GraphBlueprintOutcome(
                id="outcome_1",
                outcome="Prepare model inputs.",
                evidence="Transform a dataset into model-ready features.",
            ),
            GraphBlueprintOutcome(
                id="outcome_2",
                outcome="Evaluate predictions.",
                evidence="Compare predictions against a baseline.",
                prerequisite_ids=["outcome_1"],
            ),
        ],
    )


def _pipeline_graph(*, include_coverage: bool = True) -> ManipulateGraphResponse:
    coverage = (
        [
            GraphCoverageItem(
                outcome_id="outcome_1",
                outcome="Prepare model inputs.",
                node_ids=[3],
            ),
            GraphCoverageItem(
                outcome_id="outcome_2",
                outcome="Evaluate predictions.",
                node_ids=[4],
            ),
        ]
        if include_coverage
        else []
    )
    return ManipulateGraphResponse(
        graph_title="Model preparation and evaluation",
        plan="Prepare model inputs, then evaluate predictions.",
        coverage=coverage,
        nodes=[
            GraphNode(
                node_id=1,
                title="Machine learning",
                type=GraphType.AREA,
            ),
            GraphNode(
                node_id=2,
                title="Model workflow",
                type=GraphType.TOPIC,
            ),
            GraphNode(
                node_id=3,
                title="Prepare model inputs",
                description="Transform a dataset into model-ready features.",
                type=GraphType.CONCEPT,
                level="foundation",
            ),
            GraphNode(
                node_id=4,
                title="Evaluate predictions",
                description="Compare predictions against a baseline.",
                type=GraphType.CONCEPT,
                level="core",
            ),
        ],
        edges=[
            GraphEdge(
                source_node=1,
                target_node=2,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=2,
                target_node=3,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=2,
                target_node=4,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=3,
                target_node=4,
                type=EdgeType.PREREQUISITE,
                weight=1.0,
            ),
        ],
    )


def test_server_graph_pipeline_runs_plan_create_and_quality_retry():
    plan = _pipeline_blueprint()
    valid_graph = _pipeline_graph()
    invalid_graph = _pipeline_graph(include_coverage=False)
    provider = AiProvider(db=None, user_token="test-token")
    calls = []

    async def call_ai(**kwargs):
        calls.append(kwargs)
        if kwargs["user_prompt"].startswith("MODE: PLAN"):
            return plan
        if len(calls) == 2:
            return invalid_graph
        return valid_graph

    provider.call_ai = call_ai
    result = asyncio.run(
        provider.generate_graph_pipeline(
            user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
            agent_id=uuid4(),
        )
    )

    assert len(calls) == 3
    assert calls[0]["user_prompt"].startswith("MODE: PLAN")
    assert calls[1]["user_prompt"].lstrip().startswith("MODE: CREATE")
    assert "missing_coverage_map" in calls[2]["user_prompt"]
    assert result["blueprint"]["outcomes"][1]["prerequisite_ids"] == ["outcome_1"]
    assert result["coverage"][0]["outcome_id"] == "outcome_1"


def test_server_graph_pipeline_accepts_one_safe_residual_after_three_attempts():
    plan = _pipeline_blueprint()
    graph = _pipeline_graph()
    graph.nodes.append(
        GraphNode(
            node_id=5,
            title="Check feature completeness",
            description="Check that every required model input feature is present.",
            type=GraphType.CONCEPT,
            level="foundation",
        )
    )
    graph.nodes.append(
        GraphNode(
            node_id=6,
            title="Normalize model inputs",
            description="Normalize model inputs to a consistent numeric range.",
            type=GraphType.CONCEPT,
            level="core",
        )
    )
    graph.coverage[0].node_ids.append(5)
    graph.coverage[1].node_ids.append(6)
    graph.edges.extend(
        [
            GraphEdge(
                source_node=2,
                target_node=5,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=2,
                target_node=6,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=3,
                target_node=5,
                type=EdgeType.PREREQUISITE,
            ),
            GraphEdge(
                source_node=3,
                target_node=6,
                type=EdgeType.PREREQUISITE,
            ),
            GraphEdge(
                source_node=6,
                target_node=4,
                type=EdgeType.PREREQUISITE,
            ),
        ]
    )
    provider = AiProvider(db=None, user_token="test-token")
    calls = []

    async def call_ai(**kwargs):
        calls.append(kwargs)
        return plan if kwargs["user_prompt"].startswith("MODE: PLAN") else graph

    provider.call_ai = call_ai
    result = asyncio.run(
        provider.generate_graph_pipeline(
            user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
            agent_id=uuid4(),
        )
    )

    assert len(calls) == 4
    assert not any(
        edge["source_node"] == 3 and edge["target_node"] == 4
        for edge in result["edges"]
    )
    assert result["nodes"][4]["level"] == "foundation"
    assert result["quality_fallback"] is True


def test_server_graph_pipeline_returns_best_compatible_graph_after_three_failures():
    plan = _pipeline_blueprint()
    transitive_graph = _pipeline_graph()
    transitive_graph.nodes.append(
        GraphNode(
            node_id=5,
            title="Normalize model inputs",
            description="Normalize model inputs to a consistent numeric range.",
            type=GraphType.CONCEPT,
            level="core",
        )
    )
    transitive_graph.coverage[1].node_ids.append(5)
    transitive_graph.edges.extend(
        [
            GraphEdge(
                source_node=2,
                target_node=5,
                type=EdgeType.SUBTOPIC,
            ),
            GraphEdge(
                source_node=3,
                target_node=5,
                type=EdgeType.PREREQUISITE,
            ),
            GraphEdge(
                source_node=5,
                target_node=4,
                type=EdgeType.PREREQUISITE,
            ),
        ]
    )
    invalid_graph = _pipeline_graph(include_coverage=False)
    provider = AiProvider(db=None, user_token="test-token")
    create_attempt = 0

    async def call_ai(**kwargs):
        nonlocal create_attempt
        if kwargs["user_prompt"].startswith("MODE: PLAN"):
            return plan
        create_attempt += 1
        return transitive_graph if create_attempt == 2 else invalid_graph

    provider.call_ai = call_ai
    result = asyncio.run(
        provider.generate_graph_pipeline(
            user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
            agent_id=uuid4(),
        )
    )

    assert create_attempt == 3
    assert result["quality_fallback"] is True
    assert {node["node_id"] for node in result["nodes"]} == {1, 2, 3, 4, 5}
    assert not any(
        edge["source_node"] == 3 and edge["target_node"] == 4
        for edge in result["edges"]
    )


def test_server_graph_pipeline_rejects_fallback_without_usable_nodes():
    plan = _pipeline_blueprint()
    empty_graph = ManipulateGraphResponse(
        graph_title="Empty",
        plan="Empty graph.",
        coverage=[],
        nodes=[],
        edges=[],
    )
    provider = AiProvider(db=None, user_token="test-token")

    async def call_ai(**kwargs):
        if kwargs["user_prompt"].startswith("MODE: PLAN"):
            return plan
        return empty_graph

    provider.call_ai = call_ai
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            provider.generate_graph_pipeline(
                user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
                agent_id=uuid4(),
            )
        )

    assert error.value.status_code == 422
    assert "No app-compatible graph" in error.value.detail


@pytest.mark.parametrize(
    ("failing_stage", "expected_calls"),
    [("planning", 1), ("creation", 2)],
)
def test_server_graph_pipeline_reports_model_failure_stage(
    failing_stage,
    expected_calls,
):
    provider = AiProvider(db=None, user_token="test-token")
    calls = []

    async def call_ai(**kwargs):
        calls.append(kwargs)
        if len(calls) == expected_calls:
            raise RuntimeError("Provider failure details remain server-side.")
        return _pipeline_blueprint()

    provider.call_ai = call_ai
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            provider.generate_graph_pipeline(
                user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
                agent_id=uuid4(),
            )
        )

    assert error.value.status_code == 502
    assert failing_stage in error.value.detail
    assert "Provider failure details" not in error.value.detail


def test_server_graph_audit_rejects_duplicate_coverage_text_and_non_finite_weight():
    graph = _pipeline_graph()
    graph.coverage[1].outcome = graph.coverage[0].outcome
    graph.edges[-1].weight = float("nan")

    issues = AiProvider._validate_generated_graph(graph, _pipeline_blueprint())

    assert "coverage_duplicate_text:outcome_2" in issues
    assert "invalid_weight:3,4" in issues


def test_use_ai_routes_server_create_requests_to_graph_pipeline(monkeypatch):
    class FakeAiProvider:
        def __init__(self, *, db, user_token):
            pass

        async def generate_graph_pipeline(
            self,
            *,
            user_prompt,
            agent_id,
            response_language,
        ):
            return {"graph_title": "Server-generated graph"}

        async def call_ai(self, **kwargs):
            raise AssertionError("Server graph requests must use the pipeline.")

    monkeypatch.setattr(ai_router, "AiProvider", FakeAiProvider)
    monkeypatch.setattr(
        ai_router,
        "_resolve_response_language",
        lambda db, response_language: response_language,
    )

    result = asyncio.run(
        ai_router.use_ai(
            user_prompt="MODE: SERVER_CREATE\nLearner request:\nTrain a model.",
            agent_id=uuid4(),
            response_language=None,
            token="test-token",
            db=None,
        )
    )

    assert result == {"graph_title": "Server-generated graph"}


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
