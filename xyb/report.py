# generate GRAPH_REPORT.md - the human-readable audit trail
from __future__ import annotations
import re
from datetime import date
import networkx as nx


def _safe_community_name(label: str) -> str:
    """Mirrors export.safe_name so community hub filenames and report wikilinks always agree."""
    cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
    cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned or "unnamed"


def generate(
    G: nx.Graph,
    communities: dict[int, list[str]],
    cohesion_scores: dict[int, float],
    community_labels: dict[int, str],
    god_node_list: list[dict],
    surprise_list: list[dict],
    detection_result: dict,
    token_cost: dict,
    root: str,
    suggested_questions: list[dict] | None = None,
) -> str:
    today = date.today().isoformat()

    confidences = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
    total = len(confidences) or 1
    ext_pct = round(confidences.count("EXTRACTED") / total * 100)
    inf_pct = round(confidences.count("INFERRED") / total * 100)
    amb_pct = round(confidences.count("AMBIGUOUS") / total * 100)

    inf_edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("confidence") == "INFERRED"]
    inf_scores = [d.get("confidence_score", 0.5) for _, _, d in inf_edges]
    inf_avg = round(sum(inf_scores) / len(inf_scores), 2) if inf_scores else None

    lines = [
        f"# Graph Report - {root}  ({today})",
        "",
        "## Corpus Check",
    ]
    if detection_result.get("warning"):
        lines.append(f"- {detection_result['warning']}")
    else:
        lines += [
            f"- {detection_result['total_files']} files · ~{detection_result['total_words']:,} words",
            "- Verdict: corpus is large enough that graph structure adds value.",
        ]

    lines += [
        "",
        "## Summary",
        f"- {G.number_of_nodes()} nodes · {G.number_of_edges()} edges · {len(communities)} communities detected",
        f"- Extraction: {ext_pct}% EXTRACTED · {inf_pct}% INFERRED · {amb_pct}% AMBIGUOUS"
        + (f" · INFERRED: {len(inf_edges)} edges (avg confidence: {inf_avg})" if inf_avg is not None else ""),
        f"- Token cost: {token_cost.get('input', 0):,} input · {token_cost.get('output', 0):,} output",
    ]

    if communities:
        lines += ["", "## Community Hubs (Navigation)"]
        for cid in communities:
            label = community_labels.get(cid, f"Community {cid}")
            safe = _safe_community_name(label)
            lines.append(f"- [[_COMMUNITY_{safe}|{label}]]")

    lines += [
        "",
        "## God Nodes (most connected - your core abstractions)",
    ]
    for i, node in enumerate(god_node_list, 1):
        lines.append(f"{i}. `{node['label']}` - {node['edges']} edges")

    lines += ["", "## Surprising Connections (you probably didn't know these)"]
    if surprise_list:
        for s in surprise_list:
            relation = s.get("relation", "related_to")
            note = s.get("note", "")
            files = s.get("source_files", ["", ""])
            conf = s.get("confidence", "EXTRACTED")
            cscore = s.get("confidence_score")
            if conf == "INFERRED" and cscore is not None:
                conf_tag = f"INFERRED {cscore:.2f}"
            else:
                conf_tag = conf
            sem_tag = " [semantically similar]" if relation == "semantically_similar_to" else ""
            lines += [
                f"- `{s['source']}` --{relation}--> `{s['target']}`  [{conf_tag}]{sem_tag}",
                f"  {files[0]} → {files[1]}" + (f"  _{note}_" if note else ""),
            ]
    else:
        lines.append("- None detected - all connections are within the same source files.")

    hyperedges = G.graph.get("hyperedges", [])
    if hyperedges:
        lines += ["", "## Hyperedges (group relationships)"]
        for h in hyperedges:
            node_labels = ", ".join(h.get("nodes", []))
            conf = h.get("confidence", "INFERRED")
            cscore = h.get("confidence_score")
            conf_tag = f"{conf} {cscore:.2f}" if cscore is not None else conf
            lines.append(f"- **{h.get('label', h.get('id', ''))}** — {node_labels} [{conf_tag}]")

    lines += ["", "## Communities"]
    from .analyze import _is_file_node as _ifn
    for cid, nodes in communities.items():
        label = community_labels.get(cid, f"Community {cid}")
        score = cohesion_scores.get(cid, 0.0)
        real_nodes = [n for n in nodes if not _ifn(G, n)]
        display = [G.nodes[n].get("label", n) for n in real_nodes[:8]]
        suffix = f" (+{len(real_nodes)-8} more)" if len(real_nodes) > 8 else ""
        lines += [
            "",
            f"### Community {cid} - \"{label}\"",
            f"Cohesion: {score}",
            f"Nodes ({len(real_nodes)}): {', '.join(display)}{suffix}",
        ]

    ambiguous = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("confidence") == "AMBIGUOUS"]
    if ambiguous:
        lines += ["", "## Ambiguous Edges - Review These"]
        for u, v, d in ambiguous:
            ul = G.nodes[u].get("label", u)
            vl = G.nodes[v].get("label", v)
            lines += [
                f"- `{ul}` → `{vl}`  [AMBIGUOUS]",
                f"  {d.get('source_file', '')} · relation: {d.get('relation', 'unknown')}",
            ]

    from .analyze import _is_file_node, _is_concept_node

    isolated = [
        n for n in G.nodes()
        if G.degree(n) <= 1 and not _is_file_node(G, n) and not _is_concept_node(G, n)
    ]
    thin_communities = {
        cid: nodes for cid, nodes in communities.items() if len(nodes) < 3
    }
    gap_count = len(isolated) + len(thin_communities)

    if gap_count > 0 or amb_pct > 20:
        lines += ["", "## Knowledge Gaps"]
        if isolated:
            isolated_labels = [G.nodes[n].get("label", n) for n in isolated[:5]]
            suffix = f" (+{len(isolated)-5} more)" if len(isolated) > 5 else ""
            lines.append(f"- **{len(isolated)} isolated node(s):** {', '.join(f'`{l}`' for l in isolated_labels)}{suffix}")
            lines.append("  These have ≤1 connection - possible missing edges or undocumented components.")
        if thin_communities:
            for cid, nodes in thin_communities.items():
                label = community_labels.get(cid, f"Community {cid}")
                node_labels = [G.nodes[n].get("label", n) for n in nodes]
                lines.append(f"- **Thin community `{label}`** ({len(nodes)} nodes): {', '.join(f'`{l}`' for l in node_labels)}")
                lines.append("  Too small to be a meaningful cluster - may be noise or needs more connections extracted.")
        if amb_pct > 20:
            lines.append(f"- **High ambiguity: {amb_pct}% of edges are AMBIGUOUS.** Review the Ambiguous Edges section above.")

    if suggested_questions:
        lines += ["", "## Suggested Questions"]
        no_signal = len(suggested_questions) == 1 and suggested_questions[0].get("type") == "no_signal"
        if no_signal:
            lines.append(f"_{suggested_questions[0]['why']}_")
        else:
            lines.append("_Questions this graph is uniquely positioned to answer:_")
            lines.append("")
            for q in suggested_questions:
                if q.get("question"):
                    lines.append(f"- **{q['question']}**")
                    lines.append(f"  _{q['why']}_")

    return "\n".join(lines)


def render_medical_report(G):
    """Generate a structured medical condition report in Markdown."""
    import re as _re
    from datetime import date as _date
    today = _date.today().isoformat()
    
    lines = [
        f"# 病情概览报告 ({today})",
        "",
        "## 数据摘要",
        f"- 图谱节点数：{G.number_of_nodes()}",
        f"- 关系边数：{G.number_of_edges()}",
        "",
    ]

    # 1. 患者基本信息
    patients = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Patient"]
    if patients:
        lines += ["## 患者信息", ""]
        nid, pdata = patients[0]
        props = pdata.get("properties", {})
        for key, label in [("name", "姓名"), ("age", "年龄"), ("gender", "性别")]:
            val = props.get(key) or pdata.get(key)
            if val:
                lines.append(f"- **{label}**：{val}")
        lines.append("")
    else:
        lines += ["## 患者信息", "- 未检测到患者记录", ""]

    # 2. 确诊信息
    diagnoses = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Diagnosis"]
    if diagnoses:
        lines += ["## 确诊信息", ""]
        for nid, ddata in diagnoses:
            label = ddata.get("label", "")
            props = ddata.get("properties", {})
            parts = [f"**{label}**"] if label else []
            for key, pretty in [("cancer_type", "癌种"), ("tnm_stage", "TNM分期"), ("pathology", "病理类型"), ("date", "确诊日期")]:
                v = props.get(key) or ddata.get(key)
                if v:
                    parts.append(f"{pretty}：{v}")
            lines.append("- " + "；".join(parts))
        lines.append("")
    else:
        lines += ["## 确诊信息", "- 未检测到确诊信息", ""]

    # 3. 基因突变
    genes = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "GeneMutation"]
    if genes:
        lines += ["## 基因突变", ""]
        for nid, ddata in genes:
            label = ddata.get("label", "")
            variant = ddata.get("variant")
            drug_match = ddata.get("drug_match")
            line = f"- {label}"
            if variant:
                line += f" (variant: {variant})"
            if drug_match:
                line += f" → 可匹配靶向药：{drug_match}"
            lines.append(line)
        lines.append("")
    else:
        lines += ["## 基因突变", "- 未检测到基因突变信息", ""]

    # 4. 生物标志物
    biomarkers = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Biomarker"]
    if biomarkers:
        from collections import defaultdict
        groups = defaultdict(list)
        for nid, d in biomarkers:
            name = (d.get("properties", {}).get("name") or d.get("name") or "未知").upper()
            groups[name].append(d)
        lines += ["## 生物标志物", ""]
        for name, entries in sorted(groups.items()):
            lines.append(f"### {name}")
            sorted_entries = sorted(entries, key=lambda d: d.get("date", "") or "")
            for e in sorted_entries:
                val = e.get("value")
                unit = e.get("unit") or e.get("properties", {}).get("unit", "")
                date_str = e.get("date") or ""
                abnormal = e.get("properties", {}).get("abnormal")
                abnormal_mark = " ⚠️" if abnormal else ""
                line = f"- {val} {unit}{abnormal_mark}"
                if date_str:
                    line += f"（{date_str}）"
                lines.append(line)
            lines.append("")
    else:
        lines += ["## 生物标志物", "- 未检测到标志物数据", ""]

    # 5. 治疗与用药
    treatments = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Treatment"]
    medications = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Medication"]
    if treatments or medications:
        lines += ["## 治疗与用药", ""]
        if treatments:
            lines.append("### 治疗记录")
            for nid, d in treatments:
                label = d.get("label", "")
                ttype = d.get("treatment_type", "")
                date_str = d.get("date", "")
                if ttype:
                    line = f"- [{ttype}] {label}"
                else:
                    line = f"- {label}"
                if date_str:
                    line += f" （{date_str}）"
                lines.append(line)
            lines.append("")
        if medications:
            lines.append("### 用药方案")
            for nid, d in medications:
                name = d.get("name", "") or d.get("label", "")
                dose = d.get("dose", "")
                cycle = d.get("cycle", "")
                date_str = d.get("date", "")
                line = f"- {name}"
                if dose:
                    line += f" {dose}"
                if cycle:
                    line += f", 周期：{cycle}"
                if date_str:
                    line += f"（{date_str}）"
                lines.append(line)
            lines.append("")
    else:
        lines += ["## 治疗与用药", "- 未检测到治疗或用药记录", ""]

    # 6. 影像发现
    imaging = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Imaging"]
    if imaging:
        lines += ["## 影像发现", ""]
        for nid, d in imaging:
            label = d.get("label", "")
            modality = d.get("modality", "")
            date_str = d.get("date", "")
            if modality:
                line = f"- [{modality}] {label}"
            else:
                line = f"- {label}"
            if date_str:
                line += f"（{date_str}）"
            lines.append(line)
        lines.append("")
    else:
        lines += ["## 影像发现", "- 未检测到影像记录", ""]

    # 7. 时间线
    timeline = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "TimelineEvent"]
    if timeline:
        lines += ["## 时间线", ""]
        sorted_tl = sorted(timeline, key=lambda x: x[1].get("date", "") or "")
        for nid, d in sorted_tl:
            date_str = d.get("date", "未知日期")
            desc = d.get("description", "")
            related = d.get("related_nodes", [])
            line = f"- **{date_str}**：{desc}"
            if related:
                related_labels = []
                for rid in related[:3]:
                    rdata = G.nodes.get(rid, {})
                    related_labels.append(rdata.get("label", rid))
                if related_labels:
                    line += f"（关联：{', '.join(related_labels)}）"
            lines.append(line)
        lines.append("")
    else:
        lines += ["## 时间线", "- 无时间线事件记录", ""]

    # 8. 并发症与风险
    complications = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "Complication"]
    if complications:
        lines += ["## 并发症与风险", ""]
        for nid, d in complications:
            label = d.get("label", "")
            risk_level = d.get("risk_level", "")
            line = f"- {label}"
            if risk_level:
                line += f" [风险：{risk_level}]"
            lines.append(line)
        lines.append("")
    else:
        lines += ["## 并发症与风险", "- 未记录并发症信息", ""]

    # 9. 综合评估
    nutrition = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "NutritionAssessment"]
    psych = [(nid, d) for nid, d in G.nodes(data=True) if d.get("node_type") == "PsychologicalAssessment"]
    if nutrition or psych:
        lines += ["## 综合评估", ""]
        if nutrition:
            lines.append("### 营养评估")
            for nid, d in nutrition:
                lines.append(f"- {d.get('label', '')}")
            lines.append("")
        if psych:
            lines.append("### 心理评估")
            for nid, d in psych:
                lines.append(f"- {d.get('label', '')}")
            lines.append("")
    else:
        lines += ["## 综合评估", "- 未记录营养或心理评估", ""]

    # Footer
    lines += [
        "---",
        f"*报告生成时间：{today}*",
        "*本报告基于知识图谱自动生成，仅供参考，具体诊疗请遵医嘱*",
    ]

    return "\n".join(lines)


# ============================================================================
# HTML/PDF Report Export (Phase 7)
# ============================================================================

def generate_html_report(G, communities, cohesion_scores, community_labels,
                        god_node_list, surprise_list, detection_result,
                        token_cost, root, suggested_questions=None,
                        output_path=None):
    """
    Render medical report as HTML using Jinja2.
    
    Args:
        output_path: Output file path (default: f"{root}_report.html")
    
    Returns:
        Output file path
    """
    from datetime import date
    from jinja2 import Template
    from pathlib import Path
    
    # 读取 HTML 模板
    template_dir = Path(__file__).parent / "templates"
    template_file = template_dir / "report.html"
    
    if not template_file.exists():
        raise FileNotFoundError(f"HTML template not found: {template_file}")
    
    with open(template_file, 'r', encoding='utf-8') as f:
        template_str = f.read()
    
    # 收集图谱数据
    ctx = {
        "root": root,
        "date": date.today().isoformat(),
        "summary": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "communities": len(communities),
        },
        "patients": [],
        "diagnoses": [],
        "genes": [],
        "biomarkers": [],
        "treatments": [],
        "medications": [],
        "imaging": [],
        "timeline": [],
        "complications": [],
        "nutrition": [],
        "psychology": [],
    }
    
    for nid, d in G.nodes(data=True):
        ntype = d.get("node_type", "")
        if ntype == "Patient":
            props = d.get("properties", {})
            ctx["patients"].append({
                "name": props.get("name") or d.get("label", ""),
                "age": props.get("age", ""),
                "gender": props.get("gender", ""),
            })
        elif ntype == "Diagnosis":
            props = d.get("properties", {})
            ctx["diagnoses"].append({
                "label": d.get("label", ""),
                "cancer_type": props.get("cancer_type", ""),
                "tnm_stage": props.get("tnm_stage", ""),
                "pathology": props.get("pathology", ""),
                "date": props.get("date", ""),
            })
        elif ntype == "GeneMutation":
            ctx["genes"].append({
                "label": d.get("label", ""),
                "variant": d.get("variant", ""),
                "drug_match": d.get("drug_match", ""),
            })
        elif ntype == "Biomarker":
            props = d.get("properties", {})
            ctx["biomarkers"].append({
                "name": (props.get("name") or d.get("name", "")).upper(),
                "value": d.get("value", ""),
                "unit": d.get("unit") or props.get("unit", ""),
                "date": d.get("date", ""),
                "abnormal": props.get("abnormal", False),
            })
        elif ntype == "Treatment":
            ctx["treatments"].append({
                "label": d.get("label", ""),
                "treatment_type": d.get("treatment_type", ""),
                "date": d.get("date", ""),
            })
        elif ntype == "Medication":
            ctx["medications"].append({
                "name": d.get("name") or d.get("label", ""),
                "dose": d.get("dose", ""),
                "cycle": d.get("cycle", ""),
                "date": d.get("date", ""),
            })
        elif ntype == "Imaging":
            ctx["imaging"].append({
                "label": d.get("label", ""),
                "modality": d.get("modality", ""),
                "date": d.get("date", ""),
            })
        elif ntype == "TimelineEvent":
            ctx["timeline"].append({
                "date": d.get("date", ""),
                "description": d.get("description", ""),
            })
        elif ntype == "Complication":
            ctx["complications"].append({
                "label": d.get("label", ""),
                "risk_level": d.get("risk_level", ""),
            })
        elif ntype == "NutritionAssessment":
            ctx["nutrition"].append({"label": d.get("label", "")})
        elif ntype == "PsychologicalAssessment":
            ctx["psychology"].append({"label": d.get("label", "")})
    
    template = Template(template_str)
    html = template.render(**ctx)
    
    if output_path is None:
        output_path = f"{root}_report.html"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_path


def generate_pdf_report(G, communities, cohesion_scores, community_labels,
                       god_node_list, surprise_list, detection_result,
                       token_cost, root, suggested_questions=None,
                       output_path=None):
    """
    Generate PDF report using WeasyPrint.
    
    Args:
        output_path: Output file path (default: f"{root}_report.pdf")
    
    Returns:
        Output file path
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError("WeasyPrint required for PDF generation: pip install weasyprint")
    
    html_path = generate_html_report(G, communities, cohesion_scores, community_labels,
                                     god_node_list, surprise_list, detection_result,
                                     token_cost, root, suggested_questions)
    
    if output_path is None:
        output_path = f"{root}_report.pdf"
    
    HTML(filename=html_path).write_pdf(output_path)
    return output_path


# Patch original generate function
_original_generate = generate

def generate(
    G, communities, cohesion_scores, community_labels,
    god_node_list, surprise_list, detection_result, token_cost,
    root, suggested_questions=None,
    output_format="md",  # "md", "html", or "pdf"
    output_path=None,
):
    """
    Unified report generation with multiple output formats.
    
    Args:
        output_format: Output format - "md" (Markdown), "html", or "pdf"
        output_path: Optional custom output path
    
    Returns:
        str: Markdown content (md) or output file path (html/pdf)
    """
    if output_format == "md":
        return _original_generate(G, communities, cohesion_scores, community_labels,
                                  god_node_list, surprise_list, detection_result,
                                  token_cost, root, suggested_questions)
    elif output_format == "html":
        return generate_html_report(G, communities, cohesion_scores, community_labels,
                                   god_node_list, surprise_list, detection_result,
                                   token_cost, root, suggested_questions, output_path)
    elif output_format == "pdf":
        return generate_pdf_report(G, communities, cohesion_scores, community_labels,
                                  god_node_list, surprise_list, detection_result,
                                  token_cost, root, suggested_questions, output_path)
    else:
        raise ValueError(f"Unsupported output format: {output_format}. Use 'md', 'html', or 'pdf'")

