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
