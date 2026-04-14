"""LLM-based medical entity extraction from unstructured text and images."""
from __future__ import annotations
import base64
import json
import re
from pathlib import Path
from typing import Any

from .validate import validate_extraction


# ── Prompt templates ──────────────────────────────────────────────────────────

MEDICAL_EXTRACTION_PROMPT = """你是一个医学文档结构化提取专家。请从以下医疗文档中提取病情要素，返回严格的 JSON 格式。

文档内容：
{text}

请提取以下维度的信息（没有的字段返回 null）：
1. 基础信息：姓名、年龄、性别
2. 确诊信息：癌种、TNM分期、病理类型、确诊日期
3. 基因突变：突变位点列表（如 ["KRAS G12D", "TP53"]）
4. 标志物：检测指标及数值（如 [{{"name": "CA19-9", "value": 150, "unit": "U/mL", "date": "2024-03-15"}}])
5. 治疗记录：手术/化疗/放疗/靶向/免疫
6. 用药方案：药物名称、剂量、周期
7. 影像发现：病灶位置、尺寸变化

返回格式（严格 JSON，不要输出其他内容）：
{{
  "patient": {{"name": null, "age": null, "gender": null}},
  "diagnosis": {{"cancer_type": null, "tnm_stage": null, "pathology": null, "date": null}},
  "gene_mutations": [],
  "biomarkers": [{{"name": "...", "value": ..., "unit": "...", "date": "..."}}],
  "treatments": [{{"type": "化疗", "description": "...", "date": "..."}}],
  "medications": [{{"name": "...", "dose": "...", "cycle": "..."}}],
  "imaging_findings": [{{"description": "...", "date": "..."}}],
  "nodes": [],
  "edges": [],
  "timeline_events": [{{"date": "...", "description": "...", "related_nodes": []}}]
}}"""

IMAGE_EXTRACTION_PROMPT = """你是一个医学影像/报告识别专家。请从这张医学图片中提取所有可见的病情信息。

提取内容：
1. 患者基本信息（姓名、年龄、性别等可见信息）
2. 检查类型（CT/MRI/PET-CT/超声/病理等）
3. 检查日期
4. 检查所见/描述
5. 诊断结论
6. 标志物数值（如可见）
7. 其他医学指标

返回格式（严格 JSON）：
{{
  "patient": {{"name": null, "age": null, "gender": null}},
  "examination": {{"type": null, "date": null, "findings": null, "conclusion": null}},
  "biomarkers": [],
  "nodes": [],
  "edges": [],
  "timeline_events": []
}}"""


# ── LLM Client ────────────────────────────────────────────────────────────────

class LLMClient:
    """Simple OpenAI-compatible API client for medical extraction."""

    def __init__(self, api_base: str, api_key: str, model: str,
                 vision_model: str | None = None):
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model or model

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send chat completion request."""
        import urllib.request
        url = f"{self.api_base}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    def chat_with_image(self, image_path: Path, messages: list[dict], **kwargs) -> str:
        """Send chat with image using vision model."""
        import urllib.request
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        suffix = image_path.suffix.lower().lstrip('.')
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif",
                "webp": "webp"}.get(suffix, "jpeg")

        # Add image to last message
        last_msg = messages[-1]
        if isinstance(last_msg.get("content"), str):
            last_msg["content"] = [
                {"type": "text", "text": last_msg["content"]},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/{mime};base64,{b64}"
                }},
            ]

        url = f"{self.api_base}/chat/completions"
        payload = json.dumps({
            "model": self.vision_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]


# ── Extraction functions ──────────────────────────────────────────────────────

def _parse_llm_json(response: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    # Try to extract from ```json ... ``` blocks
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', response, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # Try direct parse
    return json.loads(response.strip())


def _raw_to_extraction(raw: dict, source_file: str) -> dict:
    """Convert raw LLM output to standard extraction format with nodes/edges."""
    nodes = list(raw.get("nodes", []))
    edges = list(raw.get("edges", []))
    timeline_events = list(raw.get("timeline_events", []))

    # Convert structured data to nodes if nodes list is empty
    if not nodes:
        nodes, edges, timeline_events = _structured_to_graph(raw, source_file)

    # Ensure source_file on all nodes
    for node in nodes:
        if "source_file" not in node:
            node["source_file"] = source_file

    return {
        "nodes": nodes,
        "edges": edges,
        "timeline_events": timeline_events,
        "source_file": source_file,
        "raw_data": raw,
    }


def _structured_to_graph(raw: dict, source_file: str) -> tuple[list, list, list]:
    """Convert structured LLM fields (patient, diagnosis, etc.) to graph nodes."""
    nodes = []
    edges = []
    timeline = []

    # Patient node
    patient = raw.get("patient") or {}
    if patient.get("name"):
        pid = f"patient_{_safe_id(patient['name'])}"
        nodes.append({
            "id": pid, "node_type": "Patient",
            "label": patient["name"],
            "source_file": source_file,
            "properties": {k: v for k, v in patient.items() if v is not None},
        })

    # Diagnosis node
    diag = raw.get("diagnosis") or {}
    if diag.get("cancer_type"):
        did = f"diagnosis_{_safe_id(diag['cancer_type'])}"
        nodes.append({
            "id": did, "node_type": "Diagnosis",
            "label": f"{diag['cancer_type']} {diag.get('tnm_stage', '')}".strip(),
            "source_file": source_file,
            "properties": {k: v for k, v in diag.items() if v is not None},
        })
        if diag.get("date"):
            timeline.append({"date": diag["date"], "description": f"确诊{diag['cancer_type']}", "related_nodes": [did]})

    # Gene mutations
    for gene in raw.get("gene_mutations") or []:
        if isinstance(gene, str):
            gid = f"gene_{_safe_id(gene)}"
            nodes.append({"id": gid, "node_type": "GeneMutation", "label": gene, "source_file": source_file})

    # Biomarkers
    for bm in raw.get("biomarkers") or []:
        if isinstance(bm, dict) and bm.get("name"):
            bid = f"biomarker_{_safe_id(bm['name'])}_{bm.get('date', 'unknown')}"
            val = bm.get("value")
            label = f"{bm['name']}: {val} {bm.get('unit', '')}" if val is not None else bm["name"]
            nodes.append({"id": bid, "node_type": "Biomarker", "label": label, "source_file": source_file,
                          "properties": bm})
            if bm.get("date"):
                timeline.append({"date": bm["date"], "description": label, "related_nodes": [bid]})

    # Treatments
    for tx in raw.get("treatments") or []:
        if isinstance(tx, dict) and tx.get("description"):
            tid = f"treatment_{_safe_id(tx['description'])}"
            nodes.append({"id": tid, "node_type": "Examination", "label": tx["description"],
                          "source_file": source_file, "properties": tx})
            if tx.get("date"):
                timeline.append({"date": tx["date"], "description": tx["description"], "related_nodes": [tid]})

    # Medications
    for med in raw.get("medications") or []:
        if isinstance(med, dict) and med.get("name"):
            mid = f"drug_{_safe_id(med['name'])}"
            label = f"{med['name']} {med.get('dose', '')}".strip()
            nodes.append({"id": mid, "node_type": "Drug", "label": label, "source_file": source_file,
                          "properties": med})

    # Imaging findings
    for img in raw.get("imaging_findings") or []:
        if isinstance(img, dict) and img.get("description"):
            iid = f"imaging_{_safe_id(img['description'][:30])}"
            nodes.append({"id": iid, "node_type": "Imaging", "label": img["description"][:80],
                          "source_file": source_file, "properties": img})
            if img.get("date"):
                timeline.append({"date": img["date"], "description": f"影像: {img['description'][:50]}", "related_nodes": [iid]})

    return nodes, edges, timeline


def _safe_id(text: str) -> str:
    """Create a safe node ID from text."""
    import re as _re
    cleaned = _re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '_', str(text))
    return cleaned.strip('_').lower()[:50]


def extract_from_text(text: str, source_file: str, llm_client: LLMClient) -> dict:
    """Extract medical entities from unstructured text using LLM."""
    if not text.strip():
        return {"nodes": [], "edges": [], "timeline_events": [], "source_file": source_file}

    # Truncate very long texts
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(truncated)"

    prompt = MEDICAL_EXTRACTION_PROMPT.format(text=text)
    messages = [
        {"role": "system", "content": "你是医学文档结构化专家，只输出 JSON，不输出其他内容。"},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm_client.chat(messages)
        raw = _parse_llm_json(response)
        return _raw_to_extraction(raw, source_file)
    except Exception as e:
        return {
            "nodes": [], "edges": [], "timeline_events": [],
            "source_file": source_file,
            "error": str(e),
        }


def extract_from_image(image_path: Path, llm_client: LLMClient) -> dict:
    """Extract medical info from image using Vision model."""
    messages = [
        {"role": "system", "content": "你是医学影像识别专家，只输出 JSON，不输出其他内容。"},
        {"role": "user", "content": IMAGE_EXTRACTION_PROMPT},
    ]

    try:
        response = llm_client.chat_with_image(image_path, messages)
        raw = _parse_llm_json(response)
        return _raw_to_extraction(raw, str(image_path))
    except Exception as e:
        return {
            "nodes": [], "edges": [], "timeline_events": [],
            "source_file": str(image_path),
            "error": str(e),
        }


def extract_xlsx_structured(sheets: list[dict], source_file: str) -> dict:
    """Extract biomarker data from xlsx sheets by matching column headers."""
    from .markers import get_all_markers, is_abnormal

    all_markers = get_all_markers()
    nodes = []
    timeline = []

    for sheet in sheets:
        rows = sheet.get("rows", [])
        if len(rows) < 2:
            continue

        header = [str(c).strip() for c in rows[0]]

        # Find columns: marker name, value, date
        name_col = value_col = date_col = unit_col = None
        for i, h in enumerate(header):
            hl = h.lower()
            if any(kw in hl for kw in ['指标', '项目', '名称', 'name', 'marker']):
                name_col = i
            elif any(kw in hl for kw in ['数值', '结果', '值', 'value', 'result']):
                value_col = i
            elif any(kw in hl for kw in ['日期', '时间', 'date']):
                date_col = i
            elif any(kw in hl for kw in ['单位', 'unit']):
                unit_col = i

        if name_col is None or value_col is None:
            continue

        for row in rows[1:]:
            if name_col >= len(row) or value_col >= len(row):
                continue
            marker_name = str(row[name_col]).strip()
            if not marker_name:
                continue

            # Try to parse value
            try:
                value = float(str(row[value_col]).strip().replace(',', ''))
            except (ValueError, TypeError):
                continue

            # Check if this matches a known marker
            matched = None
            for mk_name, mk_info in all_markers.items():
                if mk_name in marker_name or marker_name in mk_name:
                    matched = mk_name
                    break

            if not matched:
                continue

            date_str = ""
            if date_col is not None and date_col < len(row):
                date_str = str(row[date_col]).strip()

            unit = all_markers[matched]["unit"]
            abnormal = is_abnormal(matched, value)
            bid = f"biomarker_{_safe_id(matched)}_{date_str or 'nodate'}"

            label = f"{matched}: {value} {unit}"
            if abnormal:
                label += " ⚠️"

            nodes.append({
                "id": bid,
                "node_type": "Biomarker",
                "label": label,
                "source_file": source_file,
                "properties": {
                    "name": matched,
                    "value": value,
                    "unit": unit,
                    "date": date_str,
                    "abnormal": abnormal,
                }
            })

            if date_str:
                timeline.append({
                    "date": date_str,
                    "description": label,
                    "related_nodes": [bid],
                })

    return {
        "nodes": nodes,
        "edges": [],
        "timeline_events": timeline,
        "source_file": source_file,
    }


def create_llm_client_from_config(config: dict) -> LLMClient | None:
    """Create LLMClient from a config dict with api_base, api_key, model keys."""
    api_base = config.get("api_base") or config.get("base_url")
    api_key = config.get("api_key", "")
    model = config.get("model", "")
    vision_model = config.get("vision_model")

    if not api_base or not model:
        return None
    return LLMClient(api_base, api_key, model, vision_model)
