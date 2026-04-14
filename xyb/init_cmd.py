"""xyb init — standard 12-category directory generator for medical records."""
from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["get_standard_dirs", "generate_init"]

# ── Directory template ──────────────────────────────────────────────────────

_STANDARD_DIRS: list[dict[str, Any]] = [
    # 00 说明与索引
    {
        "path": "00_说明与索引",
        "readme": (
            "# 说明与索引\n\n"
            "本目录是整个病历档案的入口，包含导航说明和文件清单。\n\n"
            "## 文件\n\n"
            "- `README_如何整理.md` — 整理规范与命名约定\n"
            "- `文件清单.md` — 所有文件的索引\n"
        ),
        "files": {
            "README_如何整理.md": (
                "# 如何整理病历档案\n\n"
                "## 命名约定\n\n"
                "- 日期格式：`YYYY-MM-DD`\n"
                "- 文件名使用下划线分隔，避免空格\n"
                "- 扫描件以 `scan_` 前缀标识\n\n"
                "## 目录结构\n\n"
                "共 12 个一级分类（00–12），每个分类下有若干二级子目录。\n"
                "请将对应资料放入相应目录。\n"
            ),
            "文件清单.md": (
                "# 文件清单\n\n"
                "| 编号 | 类别 | 文件数 | 最后更新 |\n"
                "|------|------|--------|----------|\n"
                "| 00 | 说明与索引 | | |\n"
                "| 01 | 基础信息 | | |\n"
                "| 02 | 确诊信息 | | |\n"
                "| 03 | 基因与病理详情 | | |\n"
                "| 04 | 治疗记录 | | |\n"
                "| 05 | 影像资料 | | |\n"
                "| 06 | 检验指标与曲线 | | |\n"
                "| 07 | 用药方案与提醒 | | |\n"
                "| 08 | 并发症预防与风险管理 | | |\n"
                "| 09 | 营养评估 | | |\n"
                "| 10 | 心理评估 | | |\n"
                "| 11 | 随访与复发监测 | | |\n"
                "| 12 | 其他 | | |\n"
            ),
        },
    },
    # 01 基础信息
    {
        "path": "01_基础信息",
        "readme": "# 基础信息\n\n患者的基本身份信息、保险、过敏与病史。",
        "subdirs": [
            "身份信息",
            "医保与商业保险",
            "过敏史_既往史_家族史",
        ],
    },
    # 02 确诊信息
    {
        "path": "02_确诊信息",
        "readme": "# 确诊信息\n\n首诊资料、病理报告、分期评估、MDT 会诊结论。",
        "subdirs": [
            "首诊资料",
            "病理报告",
            "分期评估",
            "MDT结论",
        ],
    },
    # 03 基因与病理详情
    {
        "path": "03_基因与病理详情",
        "readme": "# 基因与病理详情\n\nNGS 报告、药物代谢基因、免疫与分子标志物。",
        "subdirs": [
            "NGS报告",
            "药敏性与药物代谢基因",
            "免疫与分子标志物",
        ],
    },
    # 药敏性子目录
    {
        "path": "03_基因与病理详情/药敏性与药物代谢基因",
        "readme": None,
        "subdirs": [
            "UGT1A1",
            "DPYD",
            "TPMT_NUDT15",
        ],
    },
    # 04 治疗记录
    {
        "path": "04_治疗记录",
        "readme": "# 治疗记录\n\n手术、化疗、放疗、靶向、免疫治疗、临床试验。",
        "subdirs": [
            "手术",
            "化疗",
            "放疗",
            "靶向",
            "免疫治疗",
            "临床试验",
        ],
    },
    # 05 影像资料
    {
        "path": "05_影像资料",
        "readme": "# 影像资料\n\nCT、MRI、PET-CT 及原始 DICOM 数据。",
        "subdirs": [
            "CT",
            "MRI",
            "PET-CT",
            "影像光盘与原始DICOM说明",
        ],
    },
    # 06 检验指标与曲线
    {
        "path": "06_检验指标与曲线",
        "readme": "# 检验指标与曲线\n\n肿瘤标志物、血常规、生化、炎症与凝血、趋势曲线。",
        "subdirs": [
            "肿瘤标志物",
            "血常规",
            "生化_肝肾功能",
            "炎症与凝血",
            "趋势曲线导出",
        ],
    },
    # 07 用药方案与提醒
    {
        "path": "07_用药方案与提醒",
        "readme": "# 用药方案与提醒\n\n当前用药、历史用药、不良反应、给药日历与复诊提醒。",
        "subdirs": [
            "当前用药清单",
            "历史用药",
            "不良反应与处理",
            "给药日历_复诊提醒",
        ],
    },
    # 08 并发症预防与风险管理
    {
        "path": "08_并发症预防与风险管理",
        "readme": "# 并发症预防与风险管理\n\n血栓/感染/出血风险、胰外分泌不足与血糖管理、急症预警卡。",
        "subdirs": [
            "血栓_感染_出血风险",
            "胰外分泌不足与血糖管理",
            "急症预警卡",
        ],
    },
    # 09 营养评估
    {
        "path": "09_营养评估",
        "readme": "# 营养评估\n\n体重与 BMI 变化、PG-SGA 营养筛查、营养干预记录。",
        "subdirs": [
            "体重与BMI变化",
            "PG-SGA_营养筛查",
            "营养干预记录",
        ],
    },
    # 10 心理评估
    {
        "path": "10_心理评估",
        "readme": "# 心理评估\n\nHADS、PHQ-9/GAD-7 量表、心理干预记录。",
        "subdirs": [
            "HADS",
            "PHQ-9_GAD-7",
            "心理干预记录",
        ],
    },
    # 11 随访与复发监测
    {
        "path": "11_随访与复发监测",
        "readme": "# 随访与复发监测\n\n随访计划、复查记录、复发/转移评估。",
        "subdirs": [
            "随访计划",
            "复查记录",
            "复发_转移评估",
        ],
    },
    # 12 其他
    {
        "path": "12_其他",
        "readme": "# 其他\n\n未归类的补充资料。",
    },
]

# Default xyb.toml content
_DEFAULT_XYB_TOML = """\
[markers]
default = ["CA19-9", "CEA", "CA125", "CA724", "CA50"]

[report]
default_format = "md"
auto_generate = true
output_dir = "xyb-out"
"""


# ── Public API ──────────────────────────────────────────────────────────────

def get_standard_dirs() -> list[dict[str, Any]]:
    """Return the full 12-category directory template."""
    return _STANDARD_DIRS


def generate_init(root: Path) -> dict[str, Any]:
    """Create the standard directory tree under *root*.

    Creates all directories, writes README files in each top-level category,
    and writes a default ``xyb.toml`` config.

    Returns a summary dict with counts of created directories and files.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    dirs_created: list[str] = []
    files_created: list[str] = []

    for entry in _STANDARD_DIRS:
        dir_path = root / entry["path"]
        dir_path.mkdir(parents=True, exist_ok=True)
        dirs_created.append(entry["path"])

        # README in this directory
        readme_content = entry.get("readme")
        if readme_content:
            readme_path = dir_path / "README.md"
            if not readme_path.exists():
                readme_path.write_text(readme_content, encoding="utf-8")
                files_created.append(str(readme_path.relative_to(root)))

        # Extra files (e.g. 文件清单.md)
        for fname, fcontent in entry.get("files", {}).items():
            fpath = dir_path / fname
            if not fpath.exists():
                fpath.write_text(fcontent, encoding="utf-8")
                files_created.append(str(fpath.relative_to(root)))

        # Sub-directories
        for subdir in entry.get("subdirs", []):
            sub_path = dir_path / subdir
            sub_path.mkdir(parents=True, exist_ok=True)
            dirs_created.append(str(sub_path.relative_to(root)))

    # xyb.toml config
    toml_path = root / "xyb.toml"
    if not toml_path.exists():
        toml_path.write_text(_DEFAULT_XYB_TOML, encoding="utf-8")
        files_created.append("xyb.toml")

    return {
        "root": str(root),
        "dirs_created": len(dirs_created),
        "files_created": len(files_created),
        "directories": dirs_created,
        "files": files_created,
    }


# ── CLI entry (for standalone testing) ──────────────────────────────────────

if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    result = generate_init(target)
    print(f"Created {result['dirs_created']} directories and {result['files_created']} files under {result['root']}")
    for d in result["directories"]:
        print(f"  [dir]  {d}")
    for f in result["files"]:
        print(f"  [file] {f}")
