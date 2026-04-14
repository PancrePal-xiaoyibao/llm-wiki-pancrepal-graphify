"""
xiaoyibao (小胰宝) CLI - 胰腺癌知识图谱管理工具
`xyb install` 配置 AI 助手 Skill 文件
`xyb init` 生成标准目录结构
`xyb process` 处理医学文档并构建图谱
`xyb report` 生成多格式报告
"""

from __future__ import annotations
import json
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("xyb")
except Exception:
    __version__ = "unknown"


def _check_skill_version(skill_dst: Path) -> None:
    """Warn if the installed skill is from an older xiaoyibao version."""
    version_file = skill_dst.parent / ".xiaoyibao_version"
    if not version_file.exists():
        return
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed != __version__:
        print(f"  warning: skill is from xiaoyibao {installed}, package is {__version__}. Run 'xyb install' to update.")


# Pre-commit hook: 如果图谱已生成，提示 AI 先阅读图谱再搜索文件
_SETTINGS_HOOK = {
    "matcher": "Glob|Grep",
    "hooks": [
        {
            "type": "command",
            "command": (
                "[ -f xiaoyibao-out/graph.json ] && "
                r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"xiaoyibao: Knowledge graph exists. Read xiaoyibao-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}}' """
                "|| true"
            ),
        }
    ],
}

# Skill 注册提示
_SKILL_REGISTRATION = (
    "
# xiaoyibao
"
    "- **xiaoyibao** (`~/.claude/skills/xiaoyibao/SKILL.md`) "
    "- pancreatic cancer knowledge graph. Trigger: `/xiaoyibao`
"
    "When the user types `/xiaoyibao`, invoke the Skill tool "
    "with `skill: "xiaoyibao"` to process medical documents and build the graph.
"
)

# 平台配置：Skill 文件复制到各 AI 助手的标准目录
_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "skill_file": "skill.md",
        "skill_dst": Path(".claude") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": True,
    },
    "codex": {
        "skill_file": "skill-codex.md",
        "skill_dst": Path(".agents") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "opencode": {
        "skill_file": "skill-opencode.md",
        "skill_dst": Path(".config") / "opencode" / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "aider": {
        "skill_file": "skill-aider.md",
        "skill_dst": Path(".aider") / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "copilot": {
        "skill_file": "skill-copilot.md",
        "skill_dst": Path(".copilot") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "claw": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".openclaw") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "droid": {
        "skill_file": "skill-droid.md",
        "skill_dst": Path(".factory") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "trae": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "trae-cn": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae-cn") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "hermes": {
        "skill_file": "skill-claw.md",  # Hermes uses OpenClaw skill format
        "skill_dst": Path(".hermes") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
    "kiro": {
        "skill_file": "skill-kiro.md",
        "skill_dst": Path(".kiro") / "skills" / "xiaoyibao" / "SKILL.md",
        "claude_md": False,
    },
}


def _copy_skill(skill_src: Path, skill_dst: Path, platform_name: str) -> None:
    """Copy skill file to destination directory."""
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dst)
    # Write version file
    version_file = skill_dst.parent / ".xiaoyibao_version"
    version_file.write_text(__version__, encoding="utf-8")
    print(f"  ✓ Installed skill for {platform_name} → {skill_dst}")


def _detect_platforms() -> list[str]:
    """Detect which AI assistants are installed."""
    detected = []
    home = Path.home()
    
    checks = {
        "claude": home / ".claude",
        "codex": home / ".agents",
        "opencode": home / ".config" / "opencode",
        "aider": home / ".aider",
        "copilot": home / ".copilot",
        "claw": home / ".openclaw",
        "droid": home / ".factory",
        "trae": home / ".trae",
        "trae-cn": home / ".trae-cn",
        "hermes": home / ".hermes",
        "kiro": home / ".kiro",
    }
    
    for platform_name, path in checks.items():
        if path.exists():
            detected.append(platform_name)
    
    return detected


def install() -> None:
    """Install xiaoyibao skills for all detected AI assistants."""
    print(f"xiaoyibao v{__version__} - Installing skills...")
    
    # Locate skill files (relative to package)
    package_dir = Path(__file__).parent
    skill_dir = package_dir
    
    detected = _detect_platforms()
    if not detected:
        print("  No AI assistant platforms detected.")
        print("  Skills will be available when you install a supported platform:")
        print("    - Claude Code: npm install -g @anthropic-ai/claude-code")
        print("    - Aider: pip install aider")
        print("    - OpenClaw: https://github.com/openclaw/openclaw")
        return
    
    print(f"  Detected platforms: {', '.join(detected)}")
    
    for platform_name in detected:
        if platform_name not in _PLATFORM_CONFIG:
            continue
        
        config = _PLATFORM_CONFIG[platform_name]
        skill_src = skill_dir / config["skill_file"]
        skill_dst = config["skill_dst"]
        
        if not skill_src.exists():
            print(f"  ⚠ Skill file not found: {skill_src}")
            continue
        
        _copy_skill(skill_src, skill_dst, platform_name)
    
    print("
✓ Installation complete!")
    print("  Restart your AI assistant to activate the xiaoyibao skill.")


def init_project(path: str | Path = ".") -> None:
    """Initialize a standard xiaoyibao directory structure."""
    from xyb.init_cmd import init_project as _init
    _init(Path(path))


def process(path: str | Path = ".") -> None:
    """Process medical documents and build knowledge graph."""
    from xyb.ingest import ingest
    from xyb.build import build
    from xyb.report import generate
    
    print("xiaoyibao: Processing medical documents...")
    # Ingest documents
    nodes = ingest(path)
    print(f"  Ingested {len(nodes)} nodes")
    
    # Build graph
    G = build(nodes)
    print(f"  Built graph with {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    # Generate reports
    generate(G, output_dir="xiaoyibao-out")
    print("  Reports saved to xiaoyibao-out/")


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("xiaoyibao CLI - Pancreatic cancer knowledge graph management")
        print("
Usage:")
        print("  xyb install              Install AI assistant skill files")
        print("  xyb init [path]          Initialize standard directory structure")
        print("  xyb process [path]       Process documents and build graph")
        print("  xyb report [--format]    Generate reports (md/html/pdf)")
        print("
For more information, see README.md")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "install":
        install()
    elif command == "init":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        init_project(path)
    elif command == "process":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        process(path)
    elif command == "report":
        from xyb.report import generate
        output_format = "all"
        if len(sys.argv) > 2:
            if sys.argv[2] in ["md", "html", "pdf", "all"]:
                output_format = sys.argv[2]
        generate(output_format=output_format)
    else:
        print(f"Unknown command: {command}")
        print("Available commands: install, init, process, report")
        sys.exit(1)


if __name__ == "__main__":
    main()
