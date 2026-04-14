"""Graph analysis: god nodes (most connected), surprising connections (cross-community), suggested questions."""
from __future__ import annotations
import networkx as nx


def _node_community_map(communities: dict[int, list[str]]) -> dict[str, int]:
    """Invert communities dict: node_id -> community_id."""
    return {n: cid for cid, nodes in communities.items() for n in nodes}


def _is_file_node(G: nx.Graph, node_id: str) -> bool:
    """
    Return True if this node is a file-level hub node (e.g. 'client', 'models')
    or an AST method stub (e.g. '.auth_flow()', '.__init__()').

    These are synthetic nodes created by the AST extractor and should be excluded
    from god nodes, surprising connections, and knowledge gap reporting.
    """
    attrs = G.nodes[node_id]
    label = attrs.get("label", "")
    if not label:
        return False
    # File-level hub: label matches the actual source filename (not just any label ending in .py)
    source_file = attrs.get("source_file", "")
    if source_file:
        from pathlib import Path as _Path
        if label == _Path(source_file).name:
            return True
    # Method stub: AST extractor labels methods as '.method_name()'
    if label.startswith(".") and label.endswith("()"):
        return True
    # Module-level function stub: labeled 'function_name()' - only has a contains edge
    # These are real functions but structurally isolated by definition; not a gap worth flagging
    if label.endswith("()") and G.degree(node_id) <= 1:
        return True
    return False


def god_nodes(G: nx.Graph, top_n: int = 10) -> list[dict]:
    """Return the top_n most-connected real entities - the core abstractions.

    File-level hub nodes are excluded: they accumulate import/contains edges
    mechanically and don't represent meaningful architectural abstractions.
    """
    degree = dict(G.degree())
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)
    result = []
    for node_id, deg in sorted_nodes:
        if _is_file_node(G, node_id) or _is_concept_node(G, node_id):
            continue
        result.append({
            "id": node_id,
            "label": G.nodes[node_id].get("label", node_id),
            "edges": deg,
        })
        if len(result) >= top_n:
            break
    return result


def surprising_connections(
    G: nx.Graph,
    communities: dict[int, list[str]] | None = None,
    top_n: int = 5,
) -> list[dict]:
    """
    Find connections that are genuinely surprising - not obvious from file structure.

    Strategy:
    - Multi-file corpora: cross-file edges between real entities (not concept nodes).
      Sorted AMBIGUOUS → INFERRED → EXTRACTED.
    - Single-file / single-source corpora: cross-community edges that bridge
      distant parts of the graph (betweenness centrality on edges).
      These reveal non-obvious structural couplings.

    Concept nodes (empty source_file, or injected semantic annotations) are excluded
    from surprising connections because they are intentional, not discovered.
    """
    # Identify unique source files (ignore empty/null source_file)
    source_files = {
        data.get("source_file", "")
        for _, data in G.nodes(data=True)
        if data.get("source_file", "")
    }
    is_multi_source = len(source_files) > 1

    if is_multi_source:
        return _cross_file_surprises(G, communities or {}, top_n)
    else:
        return _cross_community_surprises(G, communities or {}, top_n)


def _is_concept_node(G: nx.Graph, node_id: str) -> bool:
    """
    Return True if this node is a manually-injected semantic concept node
    rather than a real entity found in source code.

    Signals:
    - Empty source_file
    - source_file doesn't look like a real file path (no extension)
    """
    data = G.nodes[node_id]
    source = data.get("source_file", "")
    if not source:
        return True
    # Has no file extension → probably a concept label, not a real file
    if "." not in source.split("/")[-1]:
        return True
    return False


from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS, IMAGE_EXTENSIONS


def _file_category(path: str) -> str:
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in PAPER_EXTENSIONS:
        return "paper"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "doc"


def _top_level_dir(path: str) -> str:
    """Return the first path component - used to detect cross-repo edges."""
    return path.split("/")[0] if "/" in path else path


def _surprise_score(
    G: nx.Graph,
    u: str,
    v: str,
    data: dict,
    node_community: dict[str, int],
    u_source: str,
    v_source: str,
) -> tuple[int, list[str]]:
    """Score how surprising a cross-file edge is. Returns (score, reasons)."""
    score = 0
    reasons: list[str] = []

    # 1. Confidence weight - uncertain connections are more noteworthy
    conf = data.get("confidence", "EXTRACTED")
    conf_bonus = {"AMBIGUOUS": 3, "INFERRED": 2, "EXTRACTED": 1}.get(conf, 1)
    score += conf_bonus
    if conf in ("AMBIGUOUS", "INFERRED"):
        reasons.append(f"{conf.lower()} connection - not explicitly stated in source")

    # 2. Cross file-type bonus - code↔paper or code↔image is non-obvious
    cat_u = _file_category(u_source)
    cat_v = _file_category(v_source)
    if cat_u != cat_v:
        score += 2
        reasons.append(f"crosses file types ({cat_u} ↔ {cat_v})")

    # 3. Cross-repo bonus - different top-level directory
    if _top_level_dir(u_source) != _top_level_dir(v_source):
        score += 2
        reasons.append("connects across different repos/directories")

    # 4. Cross-community bonus - Leiden says these are structurally distant
    cid_u = node_community.get(u)
    cid_v = node_community.get(v)
    if cid_u is not None and cid_v is not None and cid_u != cid_v:
        score += 1
        reasons.append("bridges separate communities")

    # 4b. Semantic similarity bonus - non-obvious conceptual links score higher
    if data.get("relation") == "semantically_similar_to":
        score = int(score * 1.5)
        reasons.append("semantically similar concepts with no structural link")

    # 5. Peripheral→hub: a low-degree node connecting to a high-degree one
    deg_u = G.degree(u)
    deg_v = G.degree(v)
    if min(deg_u, deg_v) <= 2 and max(deg_u, deg_v) >= 5:
        score += 1
        peripheral = G.nodes[u].get("label", u) if deg_u <= 2 else G.nodes[v].get("label", v)
        hub = G.nodes[v].get("label", v) if deg_u <= 2 else G.nodes[u].get("label", u)
        reasons.append(f"peripheral node `{peripheral}` unexpectedly reaches hub `{hub}`")

    return score, reasons


def _cross_file_surprises(G: nx.Graph, communities: dict[int, list[str]], top_n: int) -> list[dict]:
    """
    Cross-file edges between real code/doc entities, ranked by a composite
    surprise score rather than confidence alone.

    Surprise score accounts for:
    - Confidence (AMBIGUOUS > INFERRED > EXTRACTED)
    - Cross file-type (code↔paper is more surprising than code↔code)
    - Cross-repo (different top-level directory)
    - Cross-community (Leiden says structurally distant)
    - Peripheral→hub (low-degree node reaching a god node)

    Each result includes a 'why' field explaining what makes it non-obvious.
    """
    node_community = _node_community_map(communities)
    candidates = []

    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        if _is_concept_node(G, u) or _is_concept_node(G, v):
            continue
        if _is_file_node(G, u) or _is_file_node(G, v):
            continue

        u_source = G.nodes[u].get("source_file", "")
        v_source = G.nodes[v].get("source_file", "")

        if not u_source or not v_source or u_source == v_source:
            continue

        score, reasons = _surprise_score(G, u, v, data, node_community, u_source, v_source)
        src_id = data.get("_src", u)
        if src_id not in G.nodes:
            src_id = u
        tgt_id = data.get("_tgt", v)
        if tgt_id not in G.nodes:
            tgt_id = v
        candidates.append({
            "_score": score,
            "source": G.nodes[src_id].get("label", src_id),
            "target": G.nodes[tgt_id].get("label", tgt_id),
            "source_files": [
                G.nodes[src_id].get("source_file", ""),
                G.nodes[tgt_id].get("source_file", ""),
            ],
            "confidence": data.get("confidence", "EXTRACTED"),
            "relation": relation,
            "why": "; ".join(reasons) if reasons else "cross-file semantic connection",
        })

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    for c in candidates:
        c.pop("_score")

    if candidates:
        return candidates[:top_n]

    return _cross_community_surprises(G, communities, top_n)


def _cross_community_surprises(
    G: nx.Graph,
    communities: dict[int, list[str]],
    top_n: int,
) -> list[dict]:
    """
    For single-source corpora: find edges that bridge different communities.
    These are surprising because Leiden grouped everything else tightly -
    these edges cut across the natural structure.

    Falls back to high-betweenness edges if no community info is provided.
    """
    if not communities:
        # No community info - use edge betweenness centrality
        if G.number_of_edges() == 0:
            return []
        betweenness = nx.edge_betweenness_centrality(G)
        top_edges = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]
        result = []
        for (u, v), score in top_edges:
            data = G.edges[u, v]
            result.append({
                "source": G.nodes[u].get("label", u),
                "target": G.nodes[v].get("label", v),
                "source_files": [
                    G.nodes[u].get("source_file", ""),
                    G.nodes[v].get("source_file", ""),
                ],
                "confidence": data.get("confidence", "EXTRACTED"),
                "relation": data.get("relation", ""),
                "note": f"Bridges graph structure (betweenness={score:.3f})",
            })
        return result

    # Build node → community map
    node_community = _node_community_map(communities)

    surprises = []
    for u, v, data in G.edges(data=True):
        cid_u = node_community.get(u)
        cid_v = node_community.get(v)
        if cid_u is None or cid_v is None or cid_u == cid_v:
            continue
        # Skip file hub nodes and plain structural edges
        if _is_file_node(G, u) or _is_file_node(G, v):
            continue
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        # This edge crosses community boundaries - interesting
        confidence = data.get("confidence", "EXTRACTED")
        src_id = data.get("_src", u)
        if src_id not in G.nodes:
            src_id = u
        tgt_id = data.get("_tgt", v)
        if tgt_id not in G.nodes:
            tgt_id = v
        surprises.append({
            "source": G.nodes[src_id].get("label", src_id),
            "target": G.nodes[tgt_id].get("label", tgt_id),
            "source_files": [
                G.nodes[src_id].get("source_file", ""),
                G.nodes[tgt_id].get("source_file", ""),
            ],
            "confidence": confidence,
            "relation": relation,
            "note": f"Bridges community {cid_u} → community {cid_v}",
            "_pair": tuple(sorted([cid_u, cid_v])),
        })

    # Sort: AMBIGUOUS first, then INFERRED, then EXTRACTED
    order = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2}
    surprises.sort(key=lambda x: order.get(x["confidence"], 3))

    # Deduplicate by community pair - one representative edge per (A→B) boundary.
    # Without this, a single high-betweenness god node dominates all results.
    seen_pairs: set[tuple] = set()
    deduped = []
    for s in surprises:
        pair = s.pop("_pair")
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            deduped.append(s)
    return deduped[:top_n]


def suggest_questions(
    G: nx.Graph,
    communities: dict[int, list[str]],
    community_labels: dict[int, str],
    top_n: int = 7,
) -> list[dict]:
    """
    Generate questions the graph is uniquely positioned to answer.
    Based on: AMBIGUOUS edges, bridge nodes, underexplored god nodes, isolated nodes.
    Each question has a 'type', 'question', and 'why' field.
    """
    questions = []
    node_community = _node_community_map(communities)

    # 1. AMBIGUOUS edges → unresolved relationship questions
    for u, v, data in G.edges(data=True):
        if data.get("confidence") == "AMBIGUOUS":
            ul = G.nodes[u].get("label", u)
            vl = G.nodes[v].get("label", v)
            relation = data.get("relation", "related to")
            questions.append({
                "type": "ambiguous_edge",
                "question": f"What is the exact relationship between `{ul}` and `{vl}`?",
                "why": f"Edge tagged AMBIGUOUS (relation: {relation}) - confidence is low.",
            })

    # 2. Bridge nodes (high betweenness) → cross-cutting concern questions
    if G.number_of_edges() > 0:
        betweenness = nx.betweenness_centrality(G)
        # Top bridge nodes that are NOT file-level hubs
        bridges = sorted(
            [(n, s) for n, s in betweenness.items()
             if not _is_file_node(G, n) and not _is_concept_node(G, n) and s > 0],
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        for node_id, score in bridges:
            label = G.nodes[node_id].get("label", node_id)
            cid = node_community.get(node_id)
            comm_label = community_labels.get(cid, f"Community {cid}") if cid is not None else "unknown"
            neighbors = list(G.neighbors(node_id))
            neighbor_comms = {node_community.get(n) for n in neighbors if node_community.get(n) != cid}
            if neighbor_comms:
                other_labels = [community_labels.get(c, f"Community {c}") for c in neighbor_comms]
                questions.append({
                    "type": "bridge_node",
                    "question": f"Why does `{label}` connect `{comm_label}` to {', '.join(f'`{l}`' for l in other_labels)}?",
                    "why": f"High betweenness centrality ({score:.3f}) - this node is a cross-community bridge.",
                })

    # 3. God nodes with many INFERRED edges → verification questions
    degree = dict(G.degree())
    top_nodes = sorted(
        [(n, d) for n, d in degree.items() if not _is_file_node(G, n)],
        key=lambda x: x[1],
        reverse=True,
    )[:5]
    for node_id, _ in top_nodes:
        inferred = [
            (u, v, d) for u, v, d in G.edges(node_id, data=True)
            if d.get("confidence") == "INFERRED"
        ]
        if len(inferred) >= 2:
            label = G.nodes[node_id].get("label", node_id)
            # Use _src/_tgt to get the correct direction; fall back to v (the other node)
            others = []
            for u, v, d in inferred[:2]:
                src_id = d.get("_src", u)
                if src_id not in G.nodes:
                    src_id = u
                tgt_id = d.get("_tgt", v)
                if tgt_id not in G.nodes:
                    tgt_id = v
                other_id = tgt_id if src_id == node_id else src_id
                others.append(G.nodes[other_id].get("label", other_id))
            questions.append({
                "type": "verify_inferred",
                "question": f"Are the {len(inferred)} inferred relationships involving `{label}` (e.g. with `{others[0]}` and `{others[1]}`) actually correct?",
                "why": f"`{label}` has {len(inferred)} INFERRED edges - model-reasoned connections that need verification.",
            })

    # 4. Isolated or weakly-connected nodes → exploration questions
    isolated = [
        n for n in G.nodes()
        if G.degree(n) <= 1 and not _is_file_node(G, n) and not _is_concept_node(G, n)
    ]
    if isolated:
        labels = [G.nodes[n].get("label", n) for n in isolated[:3]]
        questions.append({
            "type": "isolated_nodes",
            "question": f"What connects {', '.join(f'`{l}`' for l in labels)} to the rest of the system?",
            "why": f"{len(isolated)} weakly-connected nodes found - possible documentation gaps or missing edges.",
        })

    # 5. Low-cohesion communities → structural questions
    from .cluster import cohesion_score
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        if score < 0.15 and len(nodes) >= 5:
            label = community_labels.get(cid, f"Community {cid}")
            questions.append({
                "type": "low_cohesion",
                "question": f"Should `{label}` be split into smaller, more focused modules?",
                "why": f"Cohesion score {score} - nodes in this community are weakly interconnected.",
            })

    if not questions:
        return [{
            "type": "no_signal",
            "question": None,
            "why": (
                "Not enough signal to generate questions. "
                "This usually means the corpus has no AMBIGUOUS edges, no bridge nodes, "
                "no INFERRED relationships, and all communities are tightly cohesive. "
                "Add more files or run with --mode deep to extract richer edges."
            ),
        }]

    return questions[:top_n]


def graph_diff(G_old: nx.Graph, G_new: nx.Graph) -> dict:
    """Compare two graph snapshots and return what changed.

    Returns:
        {
          "new_nodes": [{"id": ..., "label": ...}],
          "removed_nodes": [{"id": ..., "label": ...}],
          "new_edges": [{"source": ..., "target": ..., "relation": ..., "confidence": ...}],
          "removed_edges": [...],
          "summary": "3 new nodes, 5 new edges, 1 node removed"
        }
    """
    old_nodes = set(G_old.nodes())
    new_nodes = set(G_new.nodes())

    added_node_ids = new_nodes - old_nodes
    removed_node_ids = old_nodes - new_nodes

    new_nodes_list = [
        {"id": n, "label": G_new.nodes[n].get("label", n)}
        for n in added_node_ids
    ]
    removed_nodes_list = [
        {"id": n, "label": G_old.nodes[n].get("label", n)}
        for n in removed_node_ids
    ]

    def edge_key(G: nx.Graph, u: str, v: str, data: dict) -> tuple:
        if G.is_directed():
            return (u, v, data.get("relation", ""))
        return (min(u, v), max(u, v), data.get("relation", ""))

    old_edge_keys = {
        edge_key(G_old, u, v, d)
        for u, v, d in G_old.edges(data=True)
    }
    new_edge_keys = {
        edge_key(G_new, u, v, d)
        for u, v, d in G_new.edges(data=True)
    }

    added_edge_keys = new_edge_keys - old_edge_keys
    removed_edge_keys = old_edge_keys - new_edge_keys

    new_edges_list = []
    for u, v, d in G_new.edges(data=True):
        if edge_key(G_new, u, v, d) in added_edge_keys:
            new_edges_list.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", ""),
            })

    removed_edges_list = []
    for u, v, d in G_old.edges(data=True):
        if edge_key(G_old, u, v, d) in removed_edge_keys:
            removed_edges_list.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", ""),
            })

    parts = []
    if new_nodes_list:
        parts.append(f"{len(new_nodes_list)} new node{'s' if len(new_nodes_list) != 1 else ''}")
    if new_edges_list:
        parts.append(f"{len(new_edges_list)} new edge{'s' if len(new_edges_list) != 1 else ''}")
    if removed_nodes_list:
        parts.append(f"{len(removed_nodes_list)} node{'s' if len(removed_nodes_list) != 1 else ''} removed")
    if removed_edges_list:
        parts.append(f"{len(removed_edges_list)} edge{'s' if len(removed_edges_list) != 1 else ''} removed")
    summary = ", ".join(parts) if parts else "no changes"

    return {
        "new_nodes": new_nodes_list,
        "removed_nodes": removed_nodes_list,
        "new_edges": new_edges_list,
        "removed_edges": removed_edges_list,
        "summary": summary,
    }


# ── Medical domain analysis ──────────────────────────────────────────────────

def flag_abnormal_markers(G: nx.Graph) -> list[dict]:
    """Check Biomarker nodes against reference ranges from markers.py.

    Returns a list of dicts:
        {node, marker, value, ref_range, status}
    where status is "high", "low", or "normal".
    Biomarker nodes without a numeric ``value`` attribute are skipped.
    """
    from .markers import get_all_markers, is_abnormal

    all_markers = get_all_markers()
    results: list[dict] = []

    for node_id, data in G.nodes(data=True):
        if data.get("node_type") != "Biomarker":
            continue
        marker_name = data.get("label", node_id)
        raw_value = data.get("value")
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (ValueError, TypeError):
            continue

        info = all_markers.get(marker_name)
        if info is None:
            # Unknown marker — flag but no reference range
            results.append({
                "node": node_id,
                "marker": marker_name,
                "value": value,
                "ref_range": "unknown",
                "status": "unknown_marker",
            })
            continue

        ref_high = info.get("ref_high")
        ref_low = info.get("ref_low")
        unit = info.get("unit", "")

        if ref_low is not None and value < ref_low:
            status = "low"
        elif ref_high is not None and value > ref_high:
            status = "high"
        else:
            status = "normal"

        range_parts = []
        if ref_low is not None:
            range_parts.append(f">={ref_low}")
        if ref_high is not None:
            range_parts.append(f"<={ref_high}")
        ref_str = " and ".join(range_parts) + f" {unit}" if unit else " and ".join(range_parts)

        results.append({
            "node": node_id,
            "marker": marker_name,
            "value": value,
            "ref_range": ref_str,
            "status": status,
        })

    return results


def missing_data_check(G: nx.Graph) -> list[dict]:
    """Identify missing or absent diagnostic categories for a patient.

    Checks which node types are present in the graph and flags common
    oncology-relevant categories that are absent (e.g. no Imaging nodes,
    no GeneMutation nodes, no recent Biomarker measurements).

    Returns a list of dicts:
        {category, present, suggestion}
    """
    from .cluster import group_by_type

    groups = group_by_type(G)

    required_categories = {
        "Imaging": "No imaging records found — consider adding CT/MRI/PET scans.",
        "GeneMutation": "No gene mutation data found — consider NGS panel or targeted testing.",
        "Biomarker": "No biomarker measurements found — consider tumor marker panels.",
        "Drug": "No medication records found — verify treatment history.",
        "Diagnosis": "No diagnosis records found — confirm pathology report.",
    }

    results: list[dict] = []

    for category, suggestion in required_categories.items():
        present = category in groups and len(groups[category]) > 0
        results.append({
            "category": category,
            "present": present,
            "suggestion": suggestion if not present else f"{len(groups[category])} record(s) found.",
        })

    # Check for stale Biomarker data (no recent measurements)
    if "Biomarker" in groups and groups["Biomarker"]:
        from datetime import datetime, timedelta
        recent_cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        recent_markers = [
            n for n in groups["Biomarker"]
            if G.nodes[n].get("date", "") >= recent_cutoff
        ]
        if not recent_markers:
            results.append({
                "category": "Biomarker (recent)",
                "present": False,
                "suggestion": f"No biomarker data within the last 6 months — consider repeat testing.",
            })
        else:
            results.append({
                "category": "Biomarker (recent)",
                "present": True,
                "suggestion": f"{len(recent_markers)} recent marker(s) found.",
            })

    # Check for recent Imaging
    if "Imaging" in groups and groups["Imaging"]:
        from datetime import datetime, timedelta
        recent_cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        recent_imaging = [
            n for n in groups["Imaging"]
            if G.nodes[n].get("date", "") >= recent_cutoff
        ]
        if not recent_imaging:
            results.append({
                "category": "Imaging (recent)",
                "present": False,
                "suggestion": "No imaging within the last 3 months — consider follow-up scans.",
            })
        else:
            results.append({
                "category": "Imaging (recent)",
                "present": True,
                "suggestion": f"{len(recent_imaging)} recent scan(s) found.",
            })

    return results


def treatment_timeline_summary(G: nx.Graph) -> list[dict]:
    """Summarize TimelineEvent nodes into a readable treatment history.

    Events are sorted by date and grouped into phases (diagnosis, surgery,
    chemotherapy, radiation, follow-up) based on label keywords.

    Returns a list of dicts:
        {date, event, label, phase}
    """
    PHASE_KEYWORDS = [
        ("diagnosis", ["diagnos", "biopsy", "pathology"]),
        ("surgery", ["surgery", "resection", "切除", "手术"]),
        ("chemotherapy", ["chemo", "化疗", "FOLFOX", "XELOX", "CAPOX", "SOX",
                          "紫杉", "顺铂", "卡铂", "吉西他滨", "培美"]),
        ("radiation", ["radiation", "放疗", "放射", "RT", "IMRT"]),
        ("immunotherapy", ["immuno", "免疫", "PD-1", "PD-L1", "pembrolizumab",
                           "nivolumab", "atezolizumab", "K药", "O药"]),
        ("targeted_therapy", ["targeted", "靶向", "TKI", "erlotinib", "gefitinib",
                              "osimertinib", "crizotinib", "alectinib",
                              "bevacizumab", "trastuzumab", "cetuximab"]),
        ("follow_up", ["follow", "复查", "复诊", "monitor", "visit"]),
    ]

    events: list[dict] = []
    for node_id, data in G.nodes(data=True):
        if data.get("node_type") != "TimelineEvent":
            continue
        date = data.get("date", "unknown")
        label = data.get("label", node_id)

        # Classify phase
        label_lower = label.lower()
        phase = "other"
        for phase_name, keywords in PHASE_KEYWORDS:
            if any(kw.lower() in label_lower for kw in keywords):
                phase = phase_name
                break

        events.append({
            "date": date,
            "event": node_id,
            "label": label,
            "phase": phase,
        })

    events.sort(key=lambda x: x["date"])
    return events


# Well-known drug interaction pairs (generic names, lowercase).
# Each tuple: (drug_a, drug_b, severity, note)
_KNOWN_INTERACTIONS: list[tuple[str, str, str, str]] = [
    ("warfarin", "aspirin", "high", "Increased bleeding risk — monitor INR closely."),
    ("warfarin", "fluconazole", "high", "Fluconazole inhibits CYP2C9 — warfarin toxicity risk."),
    ("metformin", "contrast_dye", "high", "Risk of lactic acidosis — hold metformin 48h before/after."),
    ("methotrexate", "nsaid", "high", "NSAIDs reduce methotrexate clearance — toxicity risk."),
    ("5-fluorouracil", "capecitabine", "high", "Same drug class — do not combine."),
    ("cisplatin", "aminoglycoside", "high", "Additive nephrotoxicity and ototoxicity."),
    ("vincristine", "itraconazole", "high", "Itraconazole inhibits CYP3A4 — vincristine neurotoxicity."),
    ("tyrosine_kinase_inhibitor", "proton_pump_inhibitor", "moderate",
     "PPIs reduce TKI absorption — separate dosing or avoid."),
    ("cyclophosphamide", "allopurinol", "moderate", "Allopurinol may increase cyclophosphamide toxicity."),
    ("doxorubicin", "trastuzumab", "high", "Increased cardiotoxicity — monitor LVEF."),
    ("irinotecan", "ketoconazole", "high", "Ketoconazole inhibits CYP3A4 — SN-38 toxicity risk."),
    ("tamoxifen", "fluoxetine", "moderate", "Fluoxetine inhibits CYP2D6 — reduced tamoxifen activation."),
    ("paclitaxel", "carboplatin", "moderate", "Sequence-dependent interaction — give paclitaxel first."),
    ("fluorouracil", "leucovorin", "low", "Intentional synergy — monitor for mucositis/diarrhea."),
]

# Drugs with known high-toxicity profiles (nephrotoxic, cardiotoxic, etc.)
_TOXICITY_FLAGS: dict[str, str] = {
    "cisplatin": "nephrotoxic — monitor Cr/BUN, maintain hydration.",
    "doxorubicin": "cardiotoxic — monitor LVEF, cumulative dose limit ~450 mg/m².",
    "vincristine": "neurotoxic — monitor for peripheral neuropathy, constipation.",
    "bleomycin": "pulmonary_toxic — monitor PFTs, cumulative dose limit ~400 units.",
    "cyclophosphamide": "hemorrhagic_cystitis — mesna prophylaxis, hydration.",
    "methotrexate": "hepatotoxic/myelosuppressive — leucovorin rescue, monitor LFTs/CBC.",
    "ifosfamide": "neurotoxic/hemorrhagic_cystitis — mesna prophylaxis.",
    "carboplatin": "myelosuppressive — Calvert dosing, monitor platelets.",
    "5-fluorouracil": "cardiotoxic in rare cases — monitor for chest pain, arrhythmia.",
    "capecitabine": "hand_foot_syndrome — dose adjust for toxicity.",
    "irinotecan": "delayed_diarrhea — loperamide on standby.",
    "oxaliplatin": "peripheral_neuropathy — cold avoidance during infusion.",
    "pembrolizumab": "immune_related_AEs — monitor thyroid, liver, lung function.",
    "nivolumab": "immune_related_AEs — monitor thyroid, liver, lung function.",
}


def medication_risk_scan(G: nx.Graph) -> list[dict]:
    """Check Drug nodes for known interactions or toxicity risks.

    Scans all Drug nodes in the graph and:
    1. Flags each drug with known toxicity risks.
    2. Checks all pairs of drugs against known interaction database.

    Returns a list of dicts:
        {type, drugs, severity, note}
    where type is "interaction" or "toxicity".
    """
    drug_nodes: list[tuple[str, dict]] = [
        (nid, data) for nid, data in G.nodes(data=True)
        if data.get("node_type") == "Drug"
    ]

    results: list[dict] = []

    # 1. Toxicity flags
    for node_id, data in drug_nodes:
        label = data.get("label", node_id).lower().strip()
        for tox_drug, tox_note in _TOXICITY_FLAGS.items():
            if tox_drug in label:
                results.append({
                    "type": "toxicity",
                    "drugs": [data.get("label", node_id)],
                    "severity": "high",
                    "note": tox_note,
                })

    # 2. Interaction checks (all pairs)
    if len(drug_nodes) < 2:
        return results

    for i in range(len(drug_nodes)):
        for j in range(i + 1, len(drug_nodes)):
            id_a, data_a = drug_nodes[i]
            id_b, data_b = drug_nodes[j]
            label_a = data_a.get("label", id_a).lower().strip()
            label_b = data_b.get("label", id_b).lower().strip()

            for drug1, drug2, severity, note in _KNOWN_INTERACTIONS:
                if (drug1 in label_a and drug2 in label_b) or \
                   (drug1 in label_b and drug2 in label_a):
                    results.append({
                        "type": "interaction",
                        "drugs": [data_a.get("label", id_a), data_b.get("label", id_b)],
                        "severity": severity,
                        "note": note,
                    })

    return results
