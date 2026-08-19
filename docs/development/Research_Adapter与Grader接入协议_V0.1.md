# Research Adapter 与 Grader 接入协议 V0.1

## SUT 接入方式

三种真实渠道共享同一个 `TaskSpec → RawSUTResult → ResearchSubmission` 流程。

### Web

`doubao_web` 由 Playwright 控制可见 Chrome。一个 Batch 复用浏览器和登录态，每道题调用 `startCleanConversation()` 建立新对话。只有页面确认提交后才写 checkpoint。

### HTTP API

Manifest 使用 `adapter: http_api`，`sut.options` 提供 `endpoint`、可选 `api_key_env`、`provider` 和 `product`。TrueEval POST：

```json
{"schema_version":"trueeval.http_research_request.v0.1","task_id":"...","prompt":"...","language":"zh","as_of":null,"timeout_seconds":900}
```

接口返回：

```json
{"request_id":"可选","answer":"必需","citations":[{"citation_id":"c1","url":"https://...","title":"..."}],"search_calls":3,"cost_usd":0.1}
```

密钥只写环境变量名，不写 YAML。`gold.jsonl` 不会进入请求。

### Process Agent

Manifest 使用 `adapter: process`，`sut.options.command` 为无 shell 的命令数组。进程从 stdin 读取 `trueeval.sut_process_request.v0.1`，stdout 输出 JSONL：

```jsonl
{"event":"submission_confirmed","detail":{"external_session_id":"..."}}
{"event":"result","answer":"...","citations":[],"search_calls":3}
```

缺少 `submission_confirmed` 时不能自动重试为已提交任务；缺少 result 时归类为 collection failure。

## Judge 接入

Judge Profile 支持 OpenAI-compatible Chat Completions 或 Process JSON 协议。业务 Grader 只依赖统一 Provider，不依赖模型 SDK。API Key 由 `api_key_env` 指定；锁文件只保存 Profile 与哈希。

Judge 每次调用保存 Job、Prompt 哈希、允许输入字段、原始响应、结构化 Verdict、模型实际版本和缓存键。Fixture Judge 仅允许 fixture benchmark。

## DeepResearchEval 官方 Bridge

先执行：

```bash
python3 scripts/benchmarks/fetch_deepresearcheval_official.py
```

Bridge 必须在隔离 Python 环境调用提交 `121d4c34050d0e3b0ee441c52c4467cf58ab941e` 的 `point_quality` 与 `factual_eval`。stdin 为 `trueeval.deepresearch_official_request.v0.1`，stdout 必须符合生成的 `deepresearch_official_verdict.schema.json`。TrueEval 分别保存 `official.quality_score` 和 `official.fact_ratio`，不合并总分。

## 引用评测

引用 Overlay 固定输出五项：validity、correctness、completeness、source quality、temporal validity。产品无引用、Adapter 失败、渠道不可观察、证据抓取失败分别处理。证据抓取拒绝私网、非 HTTP URL、URL 凭据和超过 5 MiB 的正文；不绕过登录、付费或阻断。

Citation Judge 结果默认带 `experimental` 校准状态。使用 `calibrate-citations` 对人工集生成报告，至少 30 条且 Cohen's kappa 不低于 0.8 才能作为正式指标。
