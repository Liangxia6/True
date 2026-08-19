# TrueEval 文档索引

## 架构

- [统一评测工作流架构设计](architecture/TrueEval统一评测工作流架构设计_2026-08-18.md)：系统边界、双适配器、长驻 Browser Worker、状态机、技术栈和实施路线。

## 产品核查

- [25 个目标产品自动化可行性核查](product-audits/25个目标产品Web自动化可行性核查_2026-08-17.md)：五个领域、25 个具体 Product Mode 的入口、渠道、状态、风险和下一步。

## Schema

- [Research MVP Benchmark 数据格式](schemas/TrueEval_Research_MVP_Benchmark数据格式_V0.1.md)：Task、Gold、Answer 和 Score 的统一格式。

## 开发规格

- [Research 测试工作流 AI 开发规格](development/TrueEval_Research测试工作流_AI开发规格_V0.2.md)：统一执行协议、Adapter SDK、状态机、Artifact、SQLite、CLI、三条评分管线、Judge 子系统、测试策略和一次性交付验收。
- [Research 实现进度](development/IMPLEMENTATION_STATUS.md)：逐阶段记录已完成能力、非正式占位能力和下一步。
- [Research Adapter 与 Grader 接入协议](development/Research_Adapter与Grader接入协议_V0.1.md)：Web、HTTP API、Process Agent、Judge 和 DeepResearchEval Bridge 的可执行协议。

## 产品适配器

- [豆包开发规格](adapters/doubao/开发规格_V0.1.md)
- [豆包使用说明](adapters/doubao/使用说明.md)

## 测试记录

- [豆包 xbench-DeepSearch 五题 Smoke Test](testing/Doubao_xbench_2505_smoke_2026-08-19.md)：真实网页执行、答案核对、引用采集与幂等恢复记录。

后续工程文档必须放入对应子目录，不再在根目录或 `outputs/` 保存重复副本。
