# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2026-04-15

### Added
- 🎯 **胰腺癌管理专用平台** - 专为胰腺癌患者病情管理设计
- 📊 四大核心引擎：资源调度、状态对齐、闭环管理、确定性输出
- 🧬 基因检测支持：MTAP、ATM、GNAS、VEGFB 等突变分析
- 📈 30+ 肿瘤标志物和代谢指标配置系统
- 🏥 并发症风险评估和营养评估模块
- 💊 用药毒性药敏性分析（UGT1A1 基因型）
- 📁 标准化 12 分类病例目录结构（`xyb init`）
- 🎨 医疗专用模板：Markdown、HTML、PDF 多格式报告

### Changed
- 🔄 项目重命名：`graphify` → `xiaoyibao` (小胰宝)
- 🎯 CLI 统一：`graphify` → `xyb` (四个核心命令)
- 🌏 语言精简：文档聚焦中英文（移除日韩文）
- 🎨 视觉升级：引入 Baoyu 设计体系和 MapleShaw 流程
- 📦 架构重构：27 个 Python 模块医疗专用化

### Fixed
- 🐛 清理所有 graphify 时代遗留引用
- 🗑️ 移除临时文件和测试数据

### Security
- 🔒 医疗数据安全框架（本地优先，零外传）
- 🛡️ 隐私保护：患者信息本地存储，LLM 仅传脱敏数据

---

## [Unreleased]

### Planned
- 📱 Web 界面：基于 Streamlit 的交互式病情管理面板
- 🔔 智能提醒：用药提醒、复查提醒、营养建议
- 🤖 AI 助手：个性化病情分析和治疗建议
- 📊 数据可视化：PyECharts 交互式图表
- 🌐 社区支持：小胰宝社区微信公众号集成
