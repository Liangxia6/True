# TrueEval Research 实现状态

> 更新时间：2026-08-19
> 实现依据：[Research 测试工作流 AI 开发规格 V0.2](TrueEval_Research测试工作流_AI开发规格_V0.2.md)

## 结论

Research MVP 的 Phase 0–5 代码链路已实现，并通过离线自动化测试。豆包 Web 已完成首轮 5 题真实 Smoke Test，5/5 成功取回答案并进入 `READY_FOR_GRADING`。真实 LLM Judge 和 DeepResearchEval 官方上游运行仍需要 API 密钥及独立 Python 环境，不能用 fixture 冒充已完成。

## 已实现

- 16 份 Canonical JSON Schema、Zod runtime validation；
- Run / Case / Attempt 状态机、提交 checkpoint、保守 resume；
- SQLite 状态库和原子 Artifact Store；
- xbench-DeepSearch、BrowseComp-ZH、DeepResearchEval Benchmark Contract；
- xbench 与 BrowseComp-ZH 官方 Prompt 语义兼容的短事实评分；
- OpenAI-compatible 与 Process 两种真实 Judge Provider，密钥仅从环境变量读取；
- JudgeJob、模型与 Prompt 哈希、原始响应、结构化 Verdict 和缓存；
- 豆包网页、通用 HTTP API、通用 Process Agent、Fake 四类 SUT Adapter；
- 一个浏览器跨任务保持打开，每题新建会话；
- Claim 派生、Citation 映射、SSRF 防护、Evidence Snapshot、坏链接/登录墙/付费墙/阻断分类；
- 引用有效性、正确性、完整性、来源质量、时间有效性五项独立指标；
- Citation Judge 校准报告（至少 30 条且 Cohen's kappa ≥ 0.8 才可升级）；
- DeepResearchEval 锁定提交的官方 Quality / Fact 进程薄包装，两榜不合并；
- 渠道信息、系统失败、指标状态计数和均值报告；
- validate / run / resume / recover-doubao / refresh-doubao-citations / grade / report / status / calibrate-citations CLI；
- 离线端到端、契约、单元与安全测试。

## 不能在无凭据环境代跑的 Live 验收

1. xbench / BrowseComp-ZH 真实 Judge：需要在 Judge Profile 指定的环境变量中提供 API Key；
2. DeepResearchEval 官方双评分：需要执行 `fetch_deepresearcheval_official.py`，安装上游 `point_quality` 与 `factual_eval` 依赖，并配置官方 Bridge；
3. Citation Judge 正式化：需要 30–50 条人工标注校准集；未通过前报告固定标注 `experimental`；
4. 真实引用网页可能受 robots、登录或付费墙限制；系统只记录状态，不绕过限制。

## Live 验收记录

- 2026-08-19，豆包 Web + xbench-DeepSearch 2505 前五题：5/5 输出成功，0 个系统失败；
- 每题均使用新对话，批次内复用同一浏览器登录态；
- 首轮因提交确认条件过严产生 4 个 `SUBMISSION_UNCONFIRMED`，通过只读恢复找回已有会话，没有重复提交；
- 豆包来源标签不是普通链接，现已支持点击标签捕获原始来源 URL；5 题共采集 5 个 URL，分布为 2 / 0 / 0 / 1 / 2；
- 详细记录见 [豆包 xbench 五题 Smoke Test](../testing/Doubao_xbench_2505_smoke_2026-08-19.md)。

## 当前自动验收基线

- TypeScript typecheck：通过；
- Unit / Contract / Integration：32 项通过；
- npm high-severity audit：0；
- 三套 Benchmark Contract：通过；
- Process Agent 跨 SUT 端到端：通过；
- HTTP API Adapter Contract：通过；
- DeepResearchEval 官方进程协议：fixture Contract 通过，真实上游调用待凭据验收。
