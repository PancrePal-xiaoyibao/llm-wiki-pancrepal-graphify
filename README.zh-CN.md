# xiaoyibao (小胰宝)

[English](README.md)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

**面向胰腺癌智能管理的开源知识图谱平台。** 整合多模态医学文档、结构化病历、基因数据、治疗记录，构建可查询的知识图谱，辅助精准诊疗决策。

## ❤️回顾我们社区在病情管理方面的努力轨迹

## 路线演进

FastGPT RAG 1.0（2023）  
→ 社区化 RAG 1.0（2023–2024）  
→ get 笔记管理个人知识库（2025）  
→ Genie_report_skills（2026）  
→ ca199 toolkit（lihb 贡献）  
→ case organizer（2026.03）  
→ openclaw + graphify / llm-wiki（现在）

## ✨ 核心特性

- 📄 **多格式文档提取** - DICOM 医学影像、PDF、Office、图片、视频转录
- 🧬 **医疗实体识别** - 患者信息、诊断、基因突变、用药记录、时间线
- 🔗 **知识图谱构建** - 自动提取实体关系，推断隐含连接
- 🏘️ **社区自动聚类** - 基于图拓扑的 Leiden 算法，无需 embedding
- 📊 **多格式报告** - Markdown、HTML 交互图谱、PDF
- 🛠️ **MCP 工具集成** - 8 个医疗专用查询工具
- ⚙️ **标准目录生成** - 12 类胰腺癌档案标准化结构
- 
👉 参考项目：Speical thanks to contribution of [safishamsi/graphify](https://github.com/safishamsi/graphify](https://github.com/safishamsi/graphify)

👉 看看效果：
![](https://picgo-1302991947.cos.ap-guangzhou.myqcloud.com/images/f9e923d38912b3198772120c221f4404.png)


---

![](https://picgo-1302991947.cos.ap-guangzhou.myqcloud.com/images/20260415110525024.png) 

## 🚀 快速开始

### 安装

```bash
# 本地开发模式安装
pip install -e .

# 或直接运行
python -m xyb --help
```

### 使用

```bash
# 初始化标准目录结构
xyb init /path/to/patient_folder

# 处理医学文档，生成知识图谱
xyb process /path/to/medical_documents

# 生成报告
xyb report --format html
```

## 📁 项目结构

```
xiaoyibao/
├── xyb/                    # 核心 Python 包
│   ├── detect.py          # 文件类型检测
│   ├── extract*.py        # 多格式提取器
│   ├── build.py           # 图谱构建
│   ├── cluster.py         # 社区发现
│   ├── timeline.py        # 时间线生成
│   ├── serve.py           # MCP 服务器（16 个工具）
│   └── report.py          # 报告生成
├── tests/                 # 457 个单元测试
├── pyproject.toml        # 项目配置
└── README.md             # 英文文档
```

## 🔧 核心功能

### Phase 1 - 数据验证与清单
- `validate.py` - 提取结果验证框架
- `manifest.py` - 增量处理与缓存

### Phase 2 - 多模态提取
- **DICOM**: 医学影像元数据 (pydicom)
- **PDF**: 文本与表格 (pymupdf)
- **Office**: DOCX/XLSX (python-docx, openpyxl)
- **图像**: OCR 文字识别
- **视频**: Whisper 转录

### Phase 3 - 知识图谱
- **节点提取**: 实体抽取与属性继承
- **关系推断**: 语义相似性边（INFERRED）
- **社区聚类**: cohesion_score + Leiden
- **时间线**: 从文件名/目录提取日期，事件合并

### Phase 4 - 标准目录
12 类标准胰腺癌档案目录：
```
00-Index/      # 总索引
01-Patient/    # 患者基本信息
02-History/    # 病史
03-Imaging/     # 影像报告
04-Pathology/   # 病理报告
05-Genetics/    # 基因检测
06-Diagnosis/   # 诊断结论
07-Treatment/   # 治疗方案
08-Medications/ # 用药记录
09-Lab/        # 检验指标
10-FollowUp/   # 随访记录
11-Research/   # 文献资料
12-Admin/      # 行政文件
```

### Phase 5 - MCP 查询工具

**图谱工具** (8 个):
- `query_graph` - 查询整个图谱
- `get_node` - 获取节点详情
- `get_neighbors` - 获取邻接节点
- `get_community` - 获取社区信息
- `god_nodes` - 获取核心节点
- `graph_stats` - 图谱统计
- `shortest_path` - 最短路径
- `generate_report` - 生成图谱报告

**医疗工具** (8 个):
- `search_medical_literature` - 医学文献检索
- `query_drug_info` - 药物信息查询
- `get_treatment_guidelines` - 治疗指南
- `get_mutation_info` - 基因突变信息
- `query_drug_interactions` - 药物相互作用
- `get_biomarker_reference` - 生物标记物参考范围
- `query_clinical_trials` - 临床试验查询
- `get_diagnostic_criteria` - 诊断标准

### Phase 6 - 报告生成
- **Markdown**: 结构化文本报告
- **HTML**: 可交互图谱（D3.js 可视化）
- **PDF**: 打印友好格式（WeasyPrint）

### Phase 7 - 多平台 Skill
支持 10 个 AI 编码助手平台：
- Claude Code / Codex / OpenCode
- GitHub Copilot / Aider
- OpenClaw / Factory Droid
- Trae (国内版/国际版)
- Kiro / Hermes / Antigravity

## 🧪 测试

```bash
# 运行全部测试（457 个）
pytest tests/ -v

# 排除可选依赖测试
pytest tests/ -v --ignore=tests/test_transcribe.py
```

**测试覆盖率**: 100% 公共 API 覆盖  
**当前状态**: ✅ 457 通过 / 0 失败 / 0 错误

## 📚 文档

- [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构设计
- [CHANGELOG.md](CHANGELOG.md) - 版本更新日志
- [SECURITY.md](SECURITY.md) - 安全策略

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

<p align="center">
  <img src="https://picgo-1302991947.cos.ap-guangzhou.myqcloud.com/images/20260415113245326.png" width="400"/>
</p>

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**专为胰腺癌管理设计，由小胰宝社区维护。** 🎗️
