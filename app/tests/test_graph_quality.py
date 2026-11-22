import json
from pathlib import Path

from app.tests.graph_quality.check_graph_quality import graph_quality_problems

FIXTURE = (
    Path(__file__).parent
    / "graph_quality"
    / "fixtures"
    / "valid_study_path.json"
)


def _graph():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_quality_checker_accepts_a_valid_graph_fixture():
    assert graph_quality_problems(_graph()) == []


def test_quality_checker_treats_legacy_null_weights_as_essential():
    graph = _graph()
    for edge in graph["edges"]:
        if edge["type"] == "PREREQUISITE":
            edge["weight"] = None

    assert graph_quality_problems(graph) == []


def test_quality_checker_rejects_container_prerequisites_and_day_one_core_leaf():
    graph = _graph()
    graph["nodes"][2]["level"] = "core"
    graph["edges"].append(
        {
            "source_node": 2,
            "target_node": 4,
            "type": "PREREQUISITE",
            "weight": 1.0,
        }
    )

    problems = graph_quality_problems(graph)
    assert any("container" in problem for problem in problems)
    assert any("non-foundation leaf" in problem for problem in problems)
    assert any("day-one leaf" in problem for problem in problems)


def test_quality_checker_rejects_cycles_duplicates_and_missing_prerequisites():
    graph = _graph()
    graph["nodes"][3]["level"] = "advanced"
    graph["nodes"].append(
        {"node_id": 6, "title": "Equações lineares", "type": "CONCEPT", "level": "core"}
    )
    graph["edges"].extend(
        [
            {"source_node": 4, "target_node": 3, "type": "PREREQUISITE"},
            {"source_node": 3, "target_node": 4, "type": "PREREQUISITE"},
            {"source_node": 3, "target_node": 4, "type": "PREREQUISITE"},
        ]
    )

    problems = graph_quality_problems(graph)
    assert "prerequisite cycle" in problems
    assert any("duplicate edge" in problem for problem in problems)
    assert any("duplicate or similar titles" in problem for problem in problems)
    assert any("non-foundation leaf has no prerequisite: 6" == problem for problem in problems)


def test_quality_checker_rejects_broken_hierarchy_and_foundation_prerequisites():
    graph = _graph()
    graph["nodes"].append(
        {"node_id": 6, "title": "Tópico vazio", "type": "TOPIC", "level": "core"}
    )
    graph["edges"].extend(
        [
            {"source_node": 1, "target_node": 6, "type": "SUBTOPIC"},
            {"source_node": 4, "target_node": 3, "type": "PREREQUISITE"},
        ]
    )

    problems = graph_quality_problems(graph)
    assert "empty container: 6" in problems
    assert "foundation has prerequisite: 3" in problems
    assert "prerequisite level regression: 4->3" in problems


def test_quality_checker_detects_non_latin_duplicate_titles():
    graph = _graph()
    graph["nodes"][2]["title"] = "数学"
    graph["nodes"].append(
        {
            "node_id": 6,
            "title": "数学",
            "type": "CONCEPT",
            "level": "foundation",
        }
    )

    problems = graph_quality_problems(graph)
    assert any("duplicate or similar titles: 3, 6" == problem for problem in problems)


def test_quality_checker_rejects_invalid_hierarchy_and_transitive_edges():
    graph = _graph()
    graph["nodes"].append(
        {"node_id": 6, "title": "Órfão", "type": "CONCEPT", "level": "foundation"}
    )
    graph["edges"].extend(
        [
            {"source_node": 3, "target_node": 4, "type": "SUBTOPIC"},
            {"source_node": 3, "target_node": 5, "type": "PREREQUISITE"},
        ]
    )

    problems = graph_quality_problems(graph)
    assert "invalid hierarchy order: 3->4" in problems
    assert "invalid hierarchy parent count: 4" in problems
    assert "invalid hierarchy parent count: 6" in problems
    assert "transitive prerequisite: 3->5" in problems


def test_quality_checker_does_not_reduce_through_weak_prerequisites():
    graph = _graph()
    graph["edges"][4]["weight"] = 0.5
    graph["edges"][5]["weight"] = 0.5
    graph["edges"].append(
        {
            "source_node": 3,
            "target_node": 5,
            "type": "PREREQUISITE",
            "weight": 1.0,
        }
    )

    problems = graph_quality_problems(graph)
    assert "transitive prerequisite: 3->5" not in problems
