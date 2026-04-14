"""xiaoyibao (xyb) - 胰腺癌患者病情管理工具。

提取 · 构建 · 聚类 · 分析 · 报告
"""

def __getattr__(name):
    # Lazy imports so `xyb install` works before heavy deps are in place.
    # 同时兼容旧名 xiaoyibao，避免破坏现有脚本
    _map = {
        # --- 核心提取 ---
        "extract": ("xyb.extract", "extract"),
        "collect_files": ("xyb.extract", "collect_files"),
        # --- 图谱构建 ---
        "build_from_json": ("xyb.build", "build_from_json"),
        "build": ("xyb.build", "build"),
        # --- 社区聚类 ---
        "cluster": ("xyb.cluster", "cluster"),
        "score_all": ("xyb.cluster", "score_all"),
        "cohesion_score": ("xyb.cluster", "cohesion_score"),
        "group_by_type": ("xyb.cluster", "group_by_type"),
        "group_by_timeline": ("xyb.cluster", "group_by_timeline"),
        # --- 医疗分析 ---
        "god_nodes": ("xyb.analyze", "god_nodes"),
        "surprising_connections": ("xyb.analyze", "surprising_connections"),
        "suggest_questions": ("xyb.analyze", "suggest_questions"),
        "flag_abnormal_markers": ("xyb.analyze", "flag_abnormal_markers"),
        "missing_data_check": ("xyb.analyze", "missing_data_check"),
        "treatment_timeline_summary": ("xyb.analyze", "treatment_timeline_summary"),
        "medication_risk_scan": ("xyb.analyze", "medication_risk_scan"),
        # --- 报告生成 ---
        "generate_report": ("xyb.report", "generate"),
        "render_medical_report": ("xyb.report", "render_medical_report"),
        # --- 导出格式 ---
        "to_json": ("xyb.export", "to_json"),
        "to_html": ("xyb.export", "to_html"),
        "to_svg": ("xyb.export", "to_svg"),
        "to_canvas": ("xyb.export", "to_canvas"),
        "to_cypher": ("xyb.export", "to_cypher"),
        "to_wiki": ("xyb.wiki", "to_wiki"),
        # --- xiaoyibao 兼容（双别名） ---
        # 核心提取
        "extract_python": ("xiaoyibao.extract", "extract_python"),
        "extract_js": ("xiaoyibao.extract", "extract_js"),
        "extract_java": ("xiaoyibao.extract", "extract_java"),
        "extract_c": ("xiaoyibao.extract", "extract_c"),
        "extract_cpp": ("xiaoyibao.extract", "extract_cpp"),
        "extract_go": ("xiaoyibao.extract", "extract_go"),
        "extract_rust": ("xiaoyibao.extract", "extract_rust"),
        "extract_ruby": ("xiaoyibao.extract", "extract_ruby"),
        "extract_csharp": ("xiaoyibao.extract", "extract_csharp"),
        "extract_kotlin": ("xiaoyibao.extract", "extract_kotlin"),
        "extract_scala": ("xiaoyibao.extract", "extract_scala"),
        "extract_php": ("xiaoyibao.extract", "extract_php"),
        "extract_swift": ("xiaoyibao.extract", "extract_swift"),
        "extract_julia": ("xiaoyibao.extract", "extract_julia"),
        "extract_lua": ("xiaoyibao.extract", "extract_lua"),
        "extract_objc": ("xiaoyibao.extract", "extract_objc"),
        "extract_elixir": ("xiaoyibao.extract", "extract_elixir"),
        "extract_powershell": ("xiaoyibao.extract", "extract_powershell"),
        "extract_blade": ("xiaoyibao.extract", "extract_blade"),
        "extract_dart": ("xiaoyibao.extract", "extract_dart"),
        # 核心构建与分析（xiaoyibao 同名功能）
        "analyze": ("xiaoyibao.analyze", "analyze"),
        "cluster_graph": ("xiaoyibao.cluster", "cluster"),
        "build_graph": ("xiaoyibao.build", "build"),
        "export_graph": ("xiaoyibao.export", "export"),
        "detect_file_types": ("xiaoyibao.detect", "detect"),
        # 兼容别名：让 xyb 完全镜像 xiaoyibao 的导出
        "ingest": ("xiaoyibao.ingest", "ingest"),
        "validate": ("xiaoyibao.validate", "validate"),
        "security_check": ("xiaoyibao.security", "security_check"),
        "transcribe_audio": ("xiaoyibao.transcribe", "transcribe"),
        "generate_wiki": ("xiaoyibao.wiki", "generate_wiki"),
        "generate_html": ("xiaoyibao.export", "to_html"),
        "generate_svg": ("xiaoyibao.export", "to_svg"),
        "generate_json": ("xiaoyibao.export", "to_json"),
        "to_neo4j": ("xiaoyibao.export", "to_cypher"),
        # 重新导出 collect_files（已在前面医疗映射中，这里仅确保存在）
        "collect_files": ("xiaoyibao.extract", "collect_files"),
        # 注意：extract（通用）已在前面映射到 xyb.extract，无需重复
        # --- 医疗专用 ---
        "extract_from_text": ("xyb.extract_medical", "extract_from_text"),
        "extract_from_image": ("xyb.extract_medical", "extract_from_image"),
        "extract_xlsx_structured": ("xyb.extract_medical", "extract_xlsx_structured"),
        "MARKER_CATEGORIES": ("xyb.markers", "MARKER_CATEGORIES"),
        "get_marker_config": ("xyb.markers", "get_marker_config"),
        "validate_marker_value": ("xyb.markers", "validate_marker_value"),
        "extract_date_from_filename": ("xyb.timeline", "extract_date_from_filename"),
        "extract_date_from_dirname": ("xyb.timeline", "extract_date_from_dirname"),
        "build_timeline": ("xyb.timeline", "build_timeline"),
        "generate_init": ("xyb.init_cmd", "generate_init"),
        "get_standard_dirs": ("xyb.init_cmd", "get_standard_dirs"),
        "serve": ("xyb.serve", "serve"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'xyb' has no attribute {name!r}")
