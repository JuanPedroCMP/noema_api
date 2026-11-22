from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

CONTAINER_TYPES = {"AREA", "TOPIC"}
EDGE_TYPES = {"PREREQUISITE", "SUBTOPIC"}


def graph_quality_problems(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["graph must contain nodes and edges lists"]

    problems: list[str] = []
    nodes_by_id: dict[Any, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            problems.append("node entry must be an object")
            continue
        node_id = node.get("node_id")
        if node_id in nodes_by_id:
            problems.append(f"duplicate node id: {node_id}")
        nodes_by_id[node_id] = node

    containers = {
        node_id
        for node_id, node in nodes_by_id.items()
        if str(node.get("type", "")).upper() in CONTAINER_TYPES
    }
    prerequisite_edges: list[tuple[Any, Any]] = []
    hierarchy_parent_ids = {
        edge.get("source_node")
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("type", "")).upper() == "SUBTOPIC"
    }
    containers.update(hierarchy_parent_ids)
    prerequisite_pairs: set[tuple[Any, Any]] = set()
    incoming_prerequisites: dict[Any, list[Any]] = {}
    essential_incoming: dict[Any, list[Any]] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            problems.append("edge entry must be an object")
            continue
        edge_type = str(edge.get("type", "")).upper()
        source = edge.get("source_node")
        target = edge.get("target_node")
        if edge_type not in EDGE_TYPES:
            continue
        pair = (source, target)
        if pair in prerequisite_pairs:
            problems.append(f"duplicate edge: {source}->{target}")
        prerequisite_pairs.add(pair)
        if source == target:
            problems.append(f"self-loop: {source}")
        if source not in nodes_by_id or target not in nodes_by_id:
            problems.append(f"dangling edge: {source}->{target}")
        if edge_type != "PREREQUISITE":
            continue
        if source in containers or target in containers:
            problems.append(f"prerequisite touches a container: {source}->{target}")
        prerequisite_edges.append((source, target))
        incoming_prerequisites.setdefault(target, []).append(source)
        if (edge.get("weight") if edge.get("weight") is not None else 1.0) >= 0.7:
            essential_incoming.setdefault(target, []).append(source)

    children_by_parent: dict[Any, list[Any]] = {}
    for edge in edges:
        if (
            isinstance(edge, dict)
            and str(edge.get("type", "")).upper() == "SUBTOPIC"
            and edge.get("source_node") in nodes_by_id
            and edge.get("target_node") in nodes_by_id
        ):
            children_by_parent.setdefault(edge["source_node"], []).append(
                edge["target_node"]
            )
    leaves = [node_id for node_id in nodes_by_id if node_id not in containers]

    for node_id in leaves:
        node = nodes_by_id[node_id]
        level = str(node.get("level", "core")).lower()
        incoming = incoming_prerequisites.get(node_id, [])
        if level != "foundation" and not incoming:
            problems.append(f"non-foundation leaf has no prerequisite: {node_id}")
        if not essential_incoming.get(node_id) and level != "foundation":
            problems.append(f"day-one leaf is not foundation: {node_id}")

    def contains_cycle(edges_to_check: list[tuple[Any, Any]]) -> bool:
        adjacency: dict[Any, list[Any]] = {}
        for source, target in edges_to_check:
            adjacency.setdefault(source, []).append(target)
        visiting: set[Any] = set()
        visited: set[Any] = set()

        def has_cycle(node_id: Any) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            if any(has_cycle(target) for target in adjacency.get(node_id, [])):
                return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(has_cycle(node_id) for node_id in adjacency)

    if contains_cycle(prerequisite_edges):
        problems.append("prerequisite cycle")

    subtopic_edges = [
        (edge["source_node"], edge["target_node"])
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("type", "")).upper() == "SUBTOPIC"
        and edge.get("source_node") in nodes_by_id
        and edge.get("target_node") in nodes_by_id
    ]
    if contains_cycle(subtopic_edges):
        problems.append("SUBTOPIC cycle")

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
        (node_id, re.sub(r"[^a-z0-9]+", "", str(node.get("title", "")).lower()))
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
