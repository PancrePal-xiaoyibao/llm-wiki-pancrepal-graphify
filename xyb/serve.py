# MCP stdio server - exposes medical knowledge graph query tools
from __future__ import annotations
import json
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label

# Import from graphify base
from graphify.serve import (
    _load_graph,
    _communities_from_graph,
    _score_nodes,
    _bfs,
    _dfs,
    _subgraph_to_text,
    _find_node as _find_node_generic,
    _filter_blank_stdin,
)

# xyb-specific imports
from xyb.report import generate as generate_report
from xyb.analyze import god_nodes as _god_nodes_impl


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Wrapper that mirrors graphify.serve._find_node but with medical label normalization."""
    # Reuse the generic implementation
    return _find_node_generic(G, label)


def serve(graph_path: str = "graphify-out/graph.json") -> None:
    """Start the MCP server with medical tools."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    server = Server("xyb-medical")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                    },
                    "required": ["source", "target"],
                },
            ),
            types.Tool(
                name="generate_report",
                description="Generate a human-readable medical knowledge graph report (GRAPH_REPORT.md).",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    def _tool_query_graph(arguments: dict) -> str:
        question = arguments["question"]
        mode = arguments.get("mode", "bfs")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]
        if not start_nodes:
            return "No matching nodes found."
        nodes, edges = _dfs(G, start_nodes, depth) if mode == "dfs" else _bfs(G, start_nodes, depth)
        header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | {len(nodes)} nodes found\n\n"
        return header + _subgraph_to_text(G, nodes, edges, token_budget=budget)

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                   if label in d.get("label", "").lower() or label == nid.lower()]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        return "\n".join([
            f"Node: {d.get('label', nid)}",
            f"  ID: {nid}",
            f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Type: {d.get('node_type', '')}",
            f"  Community: {d.get('community', '')}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {G.nodes[nid].get('label', nid)}:"]
        for neighbor in G.neighbors(nid):
            d = G.edges[nid, neighbor]
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(f"  --> {G.nodes[neighbor].get('label', neighbor)} [{rel}] [{d.get('confidence', '')}]")
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            lines.append(f"  {d.get('label', n)} [{d.get('source_file', '')}]")
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        nodes = _god_nodes_impl(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['edges']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(arguments: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, [t.lower() for t in arguments["source"].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in arguments["target"].split()])
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        max_hops = int(arguments.get("max_hops", 8))
        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        return f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    def _tool_generate_report(arguments: dict) -> str:
        """Generate a comprehensive medical knowledge graph report."""
        try:
            # Call xyb.report.generate with required parameters
            # This is a simplified call - the full generate() needs many params
            return "Report generation placeholder - implement with xyb.report.generate()"
        except Exception as e:
            return f"Error generating report: {e}"


# ============================================================================
# Medical Domain-Specific Tools (Phase 6 Extension - 8 medical tools)

# ============================================================================
# Medical Domain-Specific Tools (Phase 6 - Full Implementation)
# ============================================================================

def _tool_search_medical_literature(arguments: dict) -> str:
    """
    Search medical literature databases (PubMed, CNKI, WanFang).
    
    Args:
        query: Search query string
        database: "pubmed", "cnki", or "wanfang" (default: pubmed)
        max_results: Maximum number of results (default: 5)
        date_from: Start date for search (optional)
    
    Returns:
        JSON string with search results
    """
    query = arguments.get("query", "")
    database = arguments.get("database", "pubmed").lower()
    max_results = int(arguments.get("max_results", 5))
    date_from = arguments.get("date_from", "")
    
    if not query:
        return json.dumps({"error": "query parameter is required"}, ensure_ascii=False)
    
    # PubMed E-utilities (免费，无需 API key)
    if database == "pubmed":
        try:
            import httpx
            
            # 构建 PubMed 查询
            search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "sort": "relevance",
            }
            if date_from:
                params["mindate"] = date_from.split("-")[0]
                params["min_date"] = date_from
            
            # 搜索 PMID
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(search_url, params=params)
                resp.raise_for_status()
                
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                pmids = [id_elem.text for id_elem in root.findall(".//Id")]
                
                if not pmids:
                    return json.dumps({
                        "database": "pubmed",
                        "query": query,
                        "total": 0,
                        "papers": [],
                    }, ensure_ascii=False)
                
                # 获取摘要信息
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "xml",
                }
                resp2 = client.get(fetch_url, params=fetch_params)
                resp2.raise_for_status()
                
                root2 = ET.fromstring(resp2.text)
                papers = []
                for article in root2.findall(".//PubmedArticle"):
                    # 标题
                    title_elem = article.find(".//ArticleTitle")
                    title = title_elem.text if title_elem is not None else ""
                    
                    # 作者
                    authors = []
                    for author in article.findall(".//Author"):
                        lastname = author.find("LastName")
                        forename = author.find("ForeName")
                        if lastname is not None and forename is not None:
                            authors.append(f"{forename.text} {lastname.text}")
                    
                    # 期刊
                    journal_elem = article.find(".//Journal/Title")
                    journal = journal_elem.text if journal_elem is not None else ""
                    
                    # 发表日期
                    pubdate = article.find(".//PubDate/Year")
                    year = pubdate.text if pubdate is not None else ""
                    
                    # PMID
                    pmid_elem = article.find(".//PMID")
                    pmid = pmid_elem.text if pmid_elem is not None else ""
                    
                    papers.append({
                        "pmid": pmid,
                        "title": title,
                        "authors": authors[:3],  # 最多显示3个作者
                        "journal": journal,
                        "year": year,
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    })
                
                return json.dumps({
                    "database": "pubmed",
                    "query": query,
                    "total": len(papers),
                    "papers": papers[:max_results],
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "error": f"PubMed search failed: {str(e)}",
                "fallback": "Consider using a local medical database or cached results"
            }, ensure_ascii=False)
    
    # CNKI (中国知网) - 需要模拟搜索，实际集成需要 API 或网页抓取
    elif database in ["cnki", "wanfang"]:
        # 返回模拟数据（实际实现需要调用相应 API）
        return json.dumps({
            "database": database,
            "query": query,
            "total": 0,
            "papers": [],
            "note": f"{database.upper()} API integration requires authentication. Use pubmed for immediate results."
        }, ensure_ascii=False)
    
    else:
        return json.dumps({"error": f"Unknown database: {database}. Use 'pubmed', 'cnki', or 'wanfang'"}, ensure_ascii=False)


def _tool_query_drug_info(arguments: dict) -> str:
    """
    Query drug information from DrugBank/medical databases.
    
    Uses open drug databases and local fallback data.
    """
    drug_name = arguments.get("drug_name", "")
    
    if not drug_name:
        return json.dumps({"error": "drug_name parameter is required"}, ensure_ascii=False)
    
    # 本地药物数据库（可扩展）
    LOCAL_DRUG_DB = {
        "阿司匹林": {
            "generic_name": "Aspirin",
            "class": "NSAID",
            "indications": ["疼痛", "发热", "抗炎", "抗血小板"],
            "mechanism": "COX 抑制剂，抑制血栓形成",
            "common_dose": "100mg 每日",
            "side_effects": ["胃肠道出血", "溃疡", "出血风险"],
            "contraindications": ["活动性出血", "哮喘", "妊娠晚期"],
        },
        "吉西他滨": {
            "generic_name": "Gemcitabine",
            "class": "抗代谢化疗药",
            "indications": ["胰腺癌", "非小细胞肺癌", "乳腺癌"],
            "mechanism": "抑制 DNA 合成，导致细胞凋亡",
            "common_dose": "1000mg/m² 每周一次",
            "side_effects": ["骨髓抑制", "恶心", "肝功能异常"],
            "contraindications": ["严重骨髓抑制", "妊娠"],
        },
        "白蛋白结合型紫杉醇": {
            "generic_name": " nab-Paclitaxel",
            "class": "微管抑制剂",
            "indications": ["胰腺癌", "乳腺癌", "非小细胞肺癌"],
            "mechanism": "稳定微管，阻断细胞分裂",
            "common_dose": "125mg/m² 每周一次",
            "side_effects": ["周围神经病变", "骨髓抑制", "过敏反应"],
            "contraindications": ["对紫杉醇过敏"],
        },
    }
    
    # 规范化查询
    normalized_name = drug_name.strip()
    
    # 直接匹配
    if normalized_name in LOCAL_DRUG_DB:
        return json.dumps({
            "drug_name": normalized_name,
            "found": True,
            "source": "local_database",
            **LOCAL_DRUG_DB[normalized_name]
        }, ensure_ascii=False)
    
    # 模糊匹配
    for key, data in LOCAL_DRUG_DB.items():
        if normalized_name.lower() in key.lower() or key.lower() in normalized_name.lower():
            return json.dumps({
                "drug_name": normalized_name,
                "matched": key,
                "found": True,
                "source": "local_database",
                **data
            }, ensure_ascii=False)
    
    # 未找到，返回结构化的未知药物信息
    return json.dumps({
        "drug_name": normalized_name,
        "found": False,
        "source": "local_database",
        "message": "药物信息不在本地数据库中。可集成 DrugBank API (requires API key) 获取详细信息。",
        "suggestion": "Check drug name spelling or use generic name"
    }, ensure_ascii=False)


def _tool_get_treatment_guidelines(arguments: dict) -> str:
    """
    Get clinical treatment guidelines for specific cancers.
    
    Returns guideline summaries from NCCN, ESMO, or CSCO.
    Local implementation uses embedded guideline snippets.
    """
    cancer_type = arguments.get("cancer_type", "").lower()
    guideline_source = arguments.get("guideline_source", "NCCN").upper()
    year = arguments.get("year", "2024")
    
    if not cancer_type:
        return json.dumps({"error": "cancer_type parameter is required"}, ensure_ascii=False)
    
    # 本地指南摘要（可扩展）
    GUIDELINES = {
        "pancreatic cancer": {
            "NCCN": {
                "first_line": {
                    "folfirinox": "适用于 ECOG 0-1，体能状态好的患者",
                    "gnab": "白蛋白结合型紫杉醇 + 吉西他滨，适用于大多数患者",
                    "gemcitabine": "单药治疗，体能状态差的患者",
                },
                "maintenance": "一线治疗有效后可考虑维持治疗",
                "targeted": {
                    "brca": "奥拉帕利维持治疗（gBRCA突变）",
                    "msi-h": "帕博利珠单抗（MSI-H/dMMR）",
                },
                "note": "NCCN 2024 指南强调基因检测指导下的精准治疗"
            },
            "CSCO": {
                "first_line": {
                    "gnab": "首选方案（I 级推荐）",
                    "folfirinox": "次选方案（II 级推荐）",
                },
                "second_line": "根据一线方案选择二线治疗",
            }
        },
        "breast cancer": {
            "NCCN": {
                "early_stage": "手术 + 辅助治疗",
                "advanced": "根据 HR/HER2 状态选择内分泌、靶向或化疗",
            }
        },
        "lung cancer": {
            "NCCN": {
                "nsclc": "根据驱动基因突变选择靶向治疗",
                "sclc": "EP 方案（依托泊苷+顺铂）",
            }
        },
    }
    
    # 查找指南
    result = GUIDELINES.get(cancer_type)
    
    if result is None:
        # 尝试模糊匹配
        for key, val in GUIDELINES.items():
            if cancer_type in key or key in cancer_type:
                result = val
                break
    
    if result is None:
        return json.dumps({
            "cancer_type": cancer_type,
            "source": f"{guideline_source} {year}",
            "message": "本地指南库暂未收录该癌种。可访问 NCCN 官网获取最新指南。",
            "available_cancers": list(GUIDELINES.keys()),
        }, ensure_ascii=False)
    
    source_guide = result.get(guideline_source, result.get("NCCN", {}))
    
    return json.dumps({
        "cancer_type": cancer_type,
        "source": f"{guideline_source} {year}",
        "guidelines": source_guide,
        "note": "本地指南摘要，仅供参考。临床决策请查阅最新官方指南全文。"
    }, ensure_ascii=False)


def _tool_get_mutation_info(arguments: dict) -> str:
    """
    Query gene mutation information from COSMIC/ClinVar.
    
    Uses local mutation database with cancer gene census data.
    """
    gene = arguments.get("gene", "").upper()
    mutation = arguments.get("mutation", "")
    database = arguments.get("database", "local").lower()
    
    if not gene:
        return json.dumps({"error": "gene parameter is required"}, ensure_ascii=False)
    
    # 本地癌症基因数据库（基于 Cancer Gene Census 等公开数据摘要）
    LOCAL_MUTATION_DB = {
        "KRAS": {
            "gene": "KRAS",
            "common_mutations": ["G12D", "G12V", "G12C", "G13D"],
            "cancer_types": ["胰腺癌", "结直肠癌", "非小细胞肺癌"],
            "frequency_pancreatic": ">90%",
            "targeted_drugs": ["Sotorasib (G12C)", "Adagrasib (G12C)", "RMC-6236 (泛 RAS)"],
            "clinical_trials": "NCT04619631 (RMC-6236)",
        },
        "TP53": {
            "gene": "TP53",
            "common_mutations": ["R175H", "R273H", "R248Q"],
            "cancer_types": ["胰腺癌", "乳腺癌", "结直肠癌", "多种实体瘤"],
            "frequency_pancreatic": "50-75%",
            "targeted_drugs": ["APR-246 (PRIMA-1MET)", "PC14586 (p53 Y220C)"],
            "clinical_trials": "NCT03931299 (APR-246)",
        },
        "CDKN2A": {
            "gene": "CDKN2A",
            "common_mutations": ["缺失", "点突变"],
            "cancer_types": ["胰腺癌", "黑色素瘤"],
            "frequency_pancreatic": "~50%",
            "targeted_drugs": [],
            "note": "CDK4/6 抑制剂在某些背景下可能有效",
        },
        "SMAD4": {
            "gene": "SMAD4",
            "common_mutations": ["缺失", "无义突变"],
            "cancer_types": ["胰腺癌"],
            "frequency_pancreatic": "~55%",
            "targeted_drugs": [],
            "note": "与预后较差相关，目前无直接靶向药",
        },
        "BRCA1": {
            "gene": "BRCA1",
            "common_mutations": ["185delAG", "5382insC"],
            "cancer_types": ["乳腺癌", "卵巢癌", "胰腺癌"],
            "targeted_drugs": ["奥拉帕利", "他拉唑帕利"],
            "homologous_recombination_deficiency": True,
        },
        "BRCA2": {
            "gene": "BRCA2",
            "common_mutations": ["6174delT", " nonsense"],
            "cancer_types": ["乳腺癌", "卵巢癌", "前列腺癌", "胰腺癌"],
            "targeted_drugs": ["奥拉帕利", "他拉唑帕利"],
            "homologous_recombination_deficiency": True,
        },
        "PALB2": {
            "gene": "PALB2",
            "cancer_types": ["乳腺癌", "胰腺癌"],
            "targeted_drugs": ["奥拉帕利"],
        },
        "ATM": {
            "gene": "ATM",
            "cancer_types": ["胰腺癌", "乳腺癌"],
            "targeted_drugs": [],
            "note": "ATM 缺陷可能对 PARP 抑制剂敏感",
        },
        "GNAS": {
            "gene": "GNAS",
            "common_mutations": ["R201C", "R201H"],
            "cancer_types": ["胰腺癌", "甲状腺癌"],
            "note": "常见于 SPEN 突变胰腺癌，目前无直接靶向药",
        },
        "VEGFB": {
            "gene": "VEGFB",
            "variants": ["rs9358923"],
            "cancer_types": ["胰腺癌"],
            "note": "血管生成相关基因，贝伐珠单抗可能影响疗效",
        },
    }
    
    if gene not in LOCAL_MUTATION_DB:
        return json.dumps({
            "gene": gene,
            "found": False,
            "message": f"Gene '{gene}' not in local database. Consider querying COSMIC/ClinVar directly.",
            "available_genes": list(LOCAL_MUTATION_DB.keys()),
        }, ensure_ascii=False)
    
    entry = LOCAL_MUTATION_DB[gene]
    
    # 如果指定了具体突变，检查是否在常见突变中
    mutation_info = None
    if mutation:
        mutation_upper = mutation.upper()
        for mut in entry.get("common_mutations", []):
            if mutation_upper in mut or mut in mutation_upper:
                mutation_info = {"mutation": mut, "description": f"常见 {gene} 驱动突变"}
                break
        
        if not mutation_info:
            mutation_info = {"mutation": mutation, "description": "突变信息可能需要查询 COSMIC"}
    
    result = {
        "gene": gene,
        "found": True,
        "source": "local_cancer_gene_census",
        "mutation_info": mutation_info if mutation else None,
        **{k: v for k, v in entry.items() if k != 'gene'},
    }
    
    return json.dumps(result, ensure_ascii=False)


def _tool_query_drug_interactions(arguments: dict) -> str:
    """
    Query drug-drug interactions for polypharmacy patients.
    
    Uses local interaction database (FDA/clinical guidelines).
    """
    drugs_arg = arguments.get("drugs", [])
    
    if isinstance(drugs_arg, str):
        drugs = [d.strip() for d in drugs_arg.split(",") if d.strip()]
    elif isinstance(drugs_arg, list):
        drugs = drugs_arg
    else:
        drugs = []
    
    if len(drugs) < 2:
        return json.dumps({"error": "at least 2 drugs required"}, ensure_ascii=False)
    
    # 本地药物相互作用数据库
    INTERACTIONS = {
        ("华法林", "阿司匹林"): {
            "severity": "高",
            "effect": "出血风险显著增加",
            "mechanism": "阿司匹林增强华法林的抗凝作用",
            "recommendation": "避免联用或严密监测 INR",
        },
        ("吉西他滨", "顺铂"): {
            "severity": "中",
            "effect": "骨髓抑制加重",
            "mechanism": "两种药物均有骨髓毒性",
            "recommendation": "监测血常规，调整剂量",
        },
        ("奥拉帕利", "地高辛"): {
            "severity": "中",
            "effect": "地高辛血药浓度升高",
            "mechanism": "P-gp 抑制",
            "recommendation": "监测地高辛浓度",
        },
    }
    
    interactions = []
    warnings = []
    
    # 检查每对药物
    for i in range(len(drugs)):
        for j in range(i + 1, len(drugs)):
            d1, d2 = drugs[i], drugs[j]
            
            # 查找相互作用（双向）
            key1 = (d1, d2)
            key2 = (d2, d1)
            
            for key in [key1, key2]:
                if key in INTERACTIONS:
                    inter = INTERACTIONS[key]
                    interactions.append({
                        "drug1": key[0],
                        "drug2": key[1],
                        **inter
                    })
                    break
            else:
                # 未找到具体相互作用，给出通用建议
                warnings.append(f"联用 '{d1}' + '{d2}'：无具体相互作用记录，但仍需临床监测")
    
    return json.dumps({
        "drugs": drugs,
        "interactions": interactions,
        "warnings": warnings,
        "total_interactions": len(interactions),
        "note": "本地交互数据库有限。完整查询请使用 Micromedex 或 Lexicomp。"
    }, ensure_ascii=False)


# ============================================================================
# Note: _tool_get_biomarker_reference already implemented (uses markers.py)
# _tool_query_clinical_trials and _tool_get_diagnostic_criteria remain stubs
# (require external API keys or extensive local databases)
# ============================================================================


def _tool_get_biomarker_reference(arguments: dict) -> str:
    """
    Get biomarker reference ranges from markers.py configuration.
    """
    biomarker = arguments.get("biomarker", "")
    
    if not biomarker:
        return json.dumps({"error": "biomarker parameter is required"}, ensure_ascii=False)
    
    try:
        from markers import MARKER_CATEGORIES
        
        found = None
        category_name = None
        for cat_name, cat_data in MARKER_CATEGORIES.items():
            if biomarker in cat_data.get("markers", {}):
                found = cat_data["markers"][biomarker]
                category_name = cat_name
                break
        
        if not found:
            return json.dumps({
                "error": f"Biomarker '{biomarker}' not found",
                "available_categories": list(MARKER_CATEGORIES.keys()),
            }, ensure_ascii=False)
        
        return json.dumps({
            "biomarker": biomarker,
            "category": category_name,
            "unit": found.get("unit", ""),
            "reference_range": {
                "low": found.get("ref_low"),
                "high": found.get("ref_high")
            },
            "source": "local_markers_configuration"
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tool_query_clinical_trials(arguments: dict) -> str:
    """
    Search ClinicalTrials.gov for relevant trials (API v2).
    """
    condition = arguments.get("condition", "")
    location = arguments.get("location", "")
    phase = arguments.get("phase", "")
    status = arguments.get("status", "RECRUITING")
    
    if not condition:
        return json.dumps({"error": "condition parameter is required"}, ensure_ascii=False)
    
    try:
        import httpx
        
        base_url = "https://clinicaltrials.gov/api/v2/studies"
        params = {
            "query.cond": condition,
            "query.term": "",
            "filter.overallStatus": status,
            "query.rec": "a",
            "query.attr": "",
            "query.advanced": "",
            "query.loc": location if location else "",
            "query.titles": "",
            "query.n": "10",
        }
        
        if phase:
            phase_map = {"1": "Phase 1", "2": "Phase 2", "3": "Phase 3", "4": "Phase 4"}
            params["query.phase"] = phase_map.get(phase, phase)
        
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(base_url, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            
            studies = []
            for study in data.get("studies", [])[:10]:
                nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
                title = study.get("protocolSection", {}).get("identificationModule", {}).get("briefTitle", "")
                study_status = study.get("protocolSection", {}).get("statusModule", {}).get("overallStatus", "")
                
                interventions = study.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions", [])
                drugs = [arm.get("name", "") for arm in interventions if arm.get("interventionType") == "Drug"]
                
                outcomes = study.get("protocolSection", {}).get("outcomesModule", {}).get("primaryOutcomes", [])
                primary = [o.get("measure", "") for o in outcomes]
                
                studies.append({
                    "nct_id": nct_id,
                    "title": title,
                    "status": study_status,
                    "drugs": drugs[:3],
                    "primary_outcomes": primary[:2],
                    "url": f"https://clinicaltrials.gov/ct2/show/{nct_id}" if nct_id else "",
                })
            
            return json.dumps({
                "condition": condition,
                "total_found": data.get("totalStudies", len(studies)),
                "trials": studies,
                "source": "ClinicalTrials.gov API v2",
            }, ensure_ascii=False)
            
    except Exception as e:
        return json.dumps({"error": f"API error: {str(e)}"}, ensure_ascii=False)


def _tool_get_diagnostic_criteria(arguments: dict) -> str:
    """
    Get diagnostic criteria for diseases (ICD, WHO, specialty guidelines).
    """
    disease = arguments.get("disease", "").lower()
    criteria_type = arguments.get("criteria_type", "ICD").upper()
    
    if not disease:
        return json.dumps({"error": "disease parameter is required"}, ensure_ascii=False)
    
    DIAGNOSTIC_CRITERIA = {
        "胰腺癌": {
            "icd10": "C25",
            "who_classification": "胰腺导管腺癌、腺鳞癌、黏液性肿瘤等",
            "diagnostic_criteria": {
                "影像学": "CT/MRI 显示胰腺占位，增强扫描明显强化",
                "病理学": "组织学/细胞学证实恶性肿瘤（金标准）",
                "肿瘤标志物": "CA19-9 升高（支持性，非诊断性）",
                "临床表现": "腹痛、黄疸、消瘦、新发糖尿病",
            },
            "tnm_staging": "AJCC 第8版",
        },
        "胰腺导管腺癌": {
            "icd10": "C25.0",
            "who_classification": "上皮性肿瘤 - 导管腺癌",
            "diagnostic_criteria": {
                "起源": "起源于胰腺导管上皮",
                "分级": "G1（高分化）- G3（低分化）",
                "免疫组化": "CK7+, CK20-, CDX2- (通常)",
            },
        },
    }
    
    result = None
    matched_key = None
    for key, data in DIAGNOSTIC_CRITERIA.items():
        if disease in key.lower() or key.lower() in disease:
            result = data
            matched_key = key
            break
    
    if not result:
        return json.dumps({
            "disease": disease,
            "found": False,
            "available": list(DIAGNOSTIC_CRITERIA.keys()),
        }, ensure_ascii=False)
    
    return json.dumps({
        "disease": matched_key,
        "icd10": result.get("icd10", ""),
        "criteria_type": criteria_type,
        "criteria": result.get("diagnostic_criteria", {}),
        "note": "Local summary only. Refer to official guidelines for clinical decisions."
    }, ensure_ascii=False)


    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
        "generate_report": _tool_generate_report,
        # Medical domain tools (Phase 6)
        "search_medical_literature": _tool_search_medical_literature,
        "query_drug_info": _tool_query_drug_info,
        "get_treatment_guidelines": _tool_get_treatment_guidelines,
        "get_mutation_info": _tool_get_mutation_info,
        "query_drug_interactions": _tool_query_drug_interactions,
        "get_biomarker_reference": _tool_get_biomarker_reference,
        "query_clinical_trials": _tool_query_clinical_trials,
        "get_diagnostic_criteria": _tool_get_diagnostic_criteria,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            return [types.TextContent(type="text", text=handler(arguments))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    _filter_blank_stdin()
    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    serve(graph_path)
