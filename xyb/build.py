# assemble node+edge dicts into a NetworkX graph, preserving edge direction
#
# Node deduplication — three layers:
#
# 1. Within a file (AST): each extractor tracks a `seen_ids` set. A node ID is
#    emitted at most once per file, so duplicate class/function definitions in
#    the same source file are collapsed to the first occurrence.
#
# 2. Between files (build): NetworkX G.add_node() is idempotent — calling it
#    twice with the same ID overwrites the attributes with the second call's
#    values. Nodes are added in extraction order (AST first, then semantic),
#    so if the same entity is extracted by both passes the semantic node
#    silently overwrites the AST node. This is intentional: semantic nodes
#    carry richer labels and cross-file context, while AST nodes have precise
#    source_location. If you need to change the priority, reorder extractions
#    passed to build().
#
# 3. Semantic merge (skill): before calling build(), the skill merges cached
#    and new semantic results using an explicit `seen` set keyed on node["id"],
#    so duplicates across cache hits and new extractions are resolved there
#    before any graph construction happens.
#
# Medical domain additions:
# - Timeline events from extraction dicts are turned into TimelineEvent nodes
#   and linked via 'contains' edges to their related_nodes.
# - Node 'properties' dicts are flattened into node attributes.

from __future__ import annotations
import hashlib
import sys
import networkx as nx
from .validate import validate_extraction


def _add_timeline_events(G: nx.Graph, extraction: dict, directed: bool) -> None:
    """Create TimelineEvent nodes from extraction['timeline_events'] and link them.

    Each timeline event becomes a TimelineEvent node with:
      - id: f"timeline_{date}_{hash}"
      - node_type: TimelineEvent
      - label: event description
      - date: event date

    An 'contains' edge is added from the event node to each related_node.
    """
    events = extraction.get("timeline_events") or []
    if not events:
        return

    node_set = set(G.nodes())

    for ev in events:
        date = ev.get("date", "")
        desc = ev.get("description", "")
        related = ev.get("related_nodes") or []

        if not date and not desc:
            continue

        # Deterministic ID from date + description
        raw = f"{date}|{desc}"
        h = hashlib.md5(raw.encode()).hexdigest()[:8]
        ev_id = f"timeline_{date}_{h}"

        # Skip if already added (from a previous extraction)
        if ev_id in node_set:
            continue

        G.add_node(ev_id, **{
            "node_type": "TimelineEvent",
            "label": desc,
            "date": date,
            "source_file": ev.get("source_file", ""),
        })
        node_set.add(ev_id)

        # Link event → related nodes via 'contains'
        for rel_id in related:
            if rel_id not in node_set:
                continue
            attrs = {"relation": "contains", "confidence": "EXTRACTED", "_src": ev_id, "_tgt": rel_id}
            G.add_edge(ev_id, rel_id, **attrs)


def _flatten_properties(G: nx.Graph) -> None:
    """Flatten 'properties' dict on nodes into individual node attributes."""
    for node_id in G.nodes():
        attrs = G.nodes[node_id]
        props = attrs.get("properties")
        if isinstance(props, dict):
            for k, v in props.items():
                # Don't overwrite core fields
                if k not in attrs:
                    attrs[k] = v


def build_from_json(extraction: dict, *, directed: bool = False) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    """
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])
    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[xiaoyibao] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    for edge in extraction.get("edges", []):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges

    # Medical domain: process timeline events
    _add_timeline_events(G, extraction, directed)

    # Flatten properties dicts into node attributes
    _flatten_properties(G)

    return G


def build(extractions: list[dict], *, directed: bool = False) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [],
                      "timeline_events": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["timeline_events"].extend(ext.get("timeline_events", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined, directed=directed)
# ========== Xiaoyibao compatibility layer ==========
# Re-export xiaoyibao.build symbols for backward compatibility
from xiaoyibao.build import (
    build_from_json,
    build,
)
