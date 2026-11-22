from __future__ import annotations

import argparse
import difflib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

CONTAINER_TYPES = {"AREA", "TOPIC"}
EDGE_TYPES = {"PREREQUISITE", "SUBTOPIC"}
NODE_TYPES = {"AREA", "TOPIC", "CONCEPT", "SUBCONCEPT"}
NODE_TYPES_ORDER = {"AREA": 0, "TOPIC": 1, "CONCEPT": 2, "SUBCONCEPT": 3}
LEVEL_ORDER = {"foundation": 0, "core": 1, "advanced": 2}


def _normalize_node_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalized_title(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _normalized_objective(value: str) -> str:
    return " ".join(value.casefold().split())


def _has_path(
    source: Any,
    target: Any,
    edges: list[tuple[Any, Any]],
) -> bool:
    adjacency: dict[Any, list[Any]] = {}
    for edge_source, edge_target in edges:
        adjacency.setdefault(edge_source, []).append(edge_target)
    pending = [source]
    visited = {source}
    while pending:
        current = pending.pop()
        for next_node in adjacency.get(current, []):
            if next_node == target:
                return True
            if next_node not in visited:
                visited.add(next_node)
                pending.append(next_node)
    return False


def graph_quality_problems(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["graph must contain nodes and edges lists"]

    problems: list[str] = []
    if not nodes:
        problems.append("graph must contain at least one node")
    if not isinstance(graph.get("graph_title"), str) or not graph["graph_title"].strip():
        problems.append("graph must have a non-empty title")

    nodes_by_id: dict[Any, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            problems.append("node entry must be an object")
            continue
        node_id = _normalize_node_id(node.get("node_id"))
        if node_id is None:
            problems.append(f"invalid node id: {node.get('node_id')}")
            continue
        if node_id in nodes_by_id:
            problems.append(f"duplicate node id: {node_id}")
        nodes_by_id[node_id] = node
        if str(node.get("type", "")).upper() not in NODE_TYPES:
            problems.append(f"invalid node type: {node_id}")
        if str(node.get("level", "core")).lower() not in LEVEL_ORDER:
            problems.append(f"invalid learning level: {node_id}")
        if not isinstance(node.get("title"), str) or not node["title"].strip():
            problems.append(f"empty node title: {node_id}")

    containers = {
        node_id
        for node_id, node in nodes_by_id.items()
        if str(node.get("type", "")).upper() in CONTAINER_TYPES
    }
    containers.update(
        _normalize_node_id(edge.get("source_node"))
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("type", "")).upper() == "SUBTOPIC"
        and _normalize_node_id(edge.get("source_node")) is not None
    )
    prerequisite_edges: list[tuple[Any, Any]] = []
    essential_prerequisite_edges: list[tuple[Any, Any]] = []
    subtopic_edges: list[tuple[Any, Any]] = []
    edge_pairs: set[tuple[Any, Any]] = set()
    incoming_prerequisites: dict[Any, list[Any]] = {}
    essential_incoming: dict[Any, list[Any]] = {}
    parents_by_child: dict[Any, set[Any]] = {}
    children_by_parent: dict[Any, list[Any]] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            problems.append("edge entry must be an object")
            continue
        edge_type = str(edge.get("type", "")).upper()
        source = _normalize_node_id(edge.get("source_node"))
        target = _normalize_node_id(edge.get("target_node"))
        if edge_type not in EDGE_TYPES:
            problems.append(f"invalid edge type: {edge_type or '<empty>'}")
            continue
        if source is None or target is None:
            problems.append(f"invalid edge endpoints: {source}->{target}")
            continue
        pair = (source, target)
        if pair in edge_pairs:
            problems.append(f"duplicate edge: {source}->{target}")
        edge_pairs.add(pair)
        if source == target:
            problems.append(f"self-loop: {source}")
        if source not in nodes_by_id or target not in nodes_by_id:
            problems.append(f"dangling edge: {source}->{target}")
            continue
        weight = edge.get("weight", 1.0)
        weight = 1.0 if weight is None else weight
        invalid_weight = (
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or not 0 <= weight <= 1
        )
        if invalid_weight:
            problems.append(f"invalid edge weight: {source}->{target}")
        if edge_type != "PREREQUISITE":
            subtopic_edges.append(pair)
            parents_by_child.setdefault(target, set()).add(source)
            children_by_parent.setdefault(source, []).append(target)
            parent_type = str(nodes_by_id[source].get("type", "")).upper()
            child_type = str(nodes_by_id[target].get("type", "")).upper()
            if (
                parent_type in NODE_TYPES
                and child_type in NODE_TYPES
                and NODE_TYPES_ORDER[parent_type] >= NODE_TYPES_ORDER[child_type]
            ):
                problems.append(f"invalid hierarchy order: {source}->{target}")
            continue
        if source in containers or target in containers:
            problems.append(f"prerequisite touches a container: {source}->{target}")
        prerequisite_edges.append((source, target))
        incoming_prerequisites.setdefault(target, []).append(source)
        if not invalid_weight and weight >= 0.7:
            essential_incoming.setdefault(target, []).append(source)
            essential_prerequisite_edges.append(pair)
        source_level = str(nodes_by_id[source].get("level", "core")).lower()
        target_level = str(nodes_by_id[target].get("level", "core")).lower()
        if (
            source_level in LEVEL_ORDER
            and target_level in LEVEL_ORDER
            and LEVEL_ORDER[source_level] > LEVEL_ORDER[target_level]
        ):
            problems.append(f"prerequisite level regression: {source}->{target}")

    for node_id, node in nodes_by_id.items():
        parent_count = len(parents_by_child.get(node_id, set()))
        node_type = str(node.get("type", "")).upper()
        if (node_type == "AREA" and parent_count > 1) or (
            node_type != "AREA" and parent_count != 1
        ):
            problems.append(f"invalid hierarchy parent count: {node_id}")
        if node_type in CONTAINER_TYPES and not children_by_parent.get(node_id):
            problems.append(f"empty container: {node_id}")
    leaves = [node_id for node_id in nodes_by_id if node_id not in containers]
    objectives: dict[str, Any] = {}

    for node_id in leaves:
        node = nodes_by_id[node_id]
        description = node.get("description")
        if not isinstance(description, str) or not description.strip():
            problems.append(f"missing learning objective: {node_id}")
        else:
            objective = _normalized_objective(description)
            if objective in objectives:
                problems.append(
                    f"duplicate learning objective: {objectives[objective]}, {node_id}"
                )
            else:
                objectives[objective] = node_id
        level = str(node.get("level", "core")).lower()
        incoming = incoming_prerequisites.get(node_id, [])
        if level == "foundation" and incoming:
            problems.append(f"foundation has prerequisite: {node_id}")
        if level != "foundation" and not incoming:
            problems.append(f"non-foundation leaf has no prerequisite: {node_id}")
        if not essential_incoming.get(node_id) and level != "foundation":
            problems.append(f"day-one leaf is not foundation: {node_id}")

    def contains_cycle(edges_to_check: list[tuple[Any, Any]]) -> bool:
        adjacency: dict[Any, list[Any]] = {}
        indegree: dict[Any, int] = {}
        for source, target in edges_to_check:
            adjacency.setdefault(source, []).append(target)
            indegree.setdefault(source, 0)
            indegree[target] = indegree.get(target, 0) + 1
        pending = [
            node_id for node_id, degree in indegree.items() if degree == 0
        ]
        visited_count = 0
        while pending:
            source = pending.pop()
            visited_count += 1
            for target in adjacency.get(source, []):
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        return visited_count != len(indegree)

    if contains_cycle(prerequisite_edges):
        problems.append("prerequisite cycle")

    if contains_cycle(subtopic_edges):
        problems.append("SUBTOPIC cycle")

    for source, target in prerequisite_edges:
        remaining_essential_edges = [
            edge
            for edge in essential_prerequisite_edges
            if edge != (source, target)
        ]
        if _has_path(source, target, remaining_essential_edges):
            problems.append(f"transitive prerequisite: {source}->{target}")

    foundation_ids = {
        node_id
        for node_id in leaves
        if str(nodes_by_id[node_id].get("level", "core")).lower()
        == "foundation"
    }
    reachable = set(foundation_ids)
    pending = list(foundation_ids)
    while pending:
        source = pending.pop()
        for prerequisite_source, target in prerequisite_edges:
            if prerequisite_source == source and target not in reachable:
                reachable.add(target)
                pending.append(target)
    for node_id in leaves:
        if node_id not in reachable:
            problems.append(f"leaf has no path from foundation: {node_id}")

    titled_nodes = [
        (node_id, _normalized_title(node.get("title", "")))
        for node_id, node in nodes_by_id.items()
    ]
    for index, (first_id, first_title) in enumerate(titled_nodes):
        if not first_title:
            continue
        for second_id, second_title in titled_nodes[index + 1 :]:
            if not second_title:
                continue
            similarity = difflib.SequenceMatcher(
                None, first_title, second_title
            ).ratio()
            if first_title == second_title or (
                min(len(first_title), len(second_title)) >= 5
                and similarity >= 0.88
            ):
                problems.append(f"duplicate or similar titles: {first_id}, {second_id}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate study-path quality in an AI graph JSON file."
    )
    parser.add_argument("json_file", type=Path)
    arguments = parser.parse_args()
    try:
        graph = json.loads(arguments.json_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read graph JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(graph, dict):
        print("graph JSON must be an object", file=sys.stderr)
        return 2

    problems = graph_quality_problems(graph)
    if problems:
        print("\n".join(f"- {problem}" for problem in problems), file=sys.stderr)
        return 1
    print("Graph quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
