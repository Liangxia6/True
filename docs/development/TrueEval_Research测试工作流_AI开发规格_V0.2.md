# TrueEval Research 测试工作流 AI 开发规格

> 版本：v0.2
> 日期：2026-08-19
> 文档性质：可直接交给开发 AI 执行的实现规格
> 当前目标：打通 Benchmark → Agent/API/Web 自动执行 → 产物冻结 → 分轨评分 → 报告
> 首个被测产品：豆包网页版深入研究
> 首批 Benchmark：xbench-DeepSearch、DeepResearchEval、BrowseComp-ZH

## 1. 文档目标

本规格定义 TrueEval Research MVP 的具体工程实现。完成后，系统必须能够：

1. 从统一 Benchmark 目录加载测试题；
2. 将题目交给不同 Agent 自动化脚本、官方 API 或网页适配器；
3. 对每道题创建隔离会话并保存不可变原始产物；
4. 将不同产品的输出归一化为统一 Research Submission；
5. 分别执行短事实、长文和引用可靠性评分；
6. 在不重新调用被测产品的情况下重新评分；
7. 输出逐题结果、失败分类和分项汇总报告；
8. 后续新增 Benchmark 或被测 Agent 时只增加适配器，不修改核心工作流。

本期不是建设自由规划的评测 Agent。调度、重试、状态转换和评分依赖由确定性代码控制；LLM 只允许用于明确声明的 Judge、Claim Extractor 或 Entailment Grader。

## 2. 已有基线与本期边界

### 2.1 当前已有能力

- `src/adapters/sut/web/doubao/` 已实现豆包单题网页自动化；
- 支持持久化 Chrome Profile、人工登录、新建对话、选择深入研究、提交 Prompt 和采集正文；
- 单题运行可保存 request、result、events、HTML、可见正文、截图和初步 citation 列表；
- `benchmarks/` 已包含三套 Benchmark 的元信息、统一 task/gold、rubric 和上游锁定信息；
- BrowseComp-ZH 与 xbench 的受保护明文只在本地生成，不进入 Git；
- DeepResearchEval 已转换为统一 JSONL。

### 2.2 当前缺口

- 豆包 CLI 直接接收 Prompt，尚未实现统一 `SUTAdapter`；
- 没有 Batch Runner、SQLite checkpoint 和进程恢复；
- 没有运行时 Schema 校验；
- 没有统一 `BenchmarkAdapter` 和 Grader Runner；
- 没有标准化 Claim、Citation、Evidence Snapshot；
- 没有将官方评分、TrueEval 评分和系统失败统一输出；
- 网页引用 URL 提取尚不完整。

### 2.3 本期不做

- 不做多机调度、Kubernetes、Temporal 或云端控制台；
- 不做多个账号的并行运行；
- 不做验证码绕过、设备验证绕过、stealth 或代理轮换；
- 不发布跨 Track 的单一 Research 总分；
- 不把修改过 Prompt 的结果冒充官方 Benchmark 结果；
- 不推测网页不可见的搜索轨迹、token 或成本；
- 不在第一期实现另外四个领域的业务评分器。

## 3. 领域与 Track 模型

Research 是 TrueEval 五大领域之一。底层数据模型将“任务类型”和“评测维度”分开：

```yaml
domain: research
track: short_fact | long_form
evaluation_overlays:
  - citation_reliability
```

对外报告可以展示三个测试区：

1. Short Fact：短事实和多跳检索；
2. Long Form：长篇研究报告；
3. Citation Reliability：引用有效性、支持度、完整性、来源质量和时效性。

Citation Reliability 是可复用 Overlay，不单独复制执行流程。它既可以评分短事实输出，也可以评分长文输出。未来专门的 Citation Stress Suite 仍使用同一个 Overlay，只是提供专门题目。

## 4. 总体架构

```mermaid
flowchart LR
    DS["Benchmark Files"] --> BA["Benchmark Adapter"]
    BA --> TS["Canonical TaskSpec"]
    TS --> OR["Run Orchestrator"]
    OR --> CR["Capability Resolver"]
    CR --> BW["Browser Worker"]
    CR --> AW["API / Process Worker"]
    BW --> SA["SUT Adapter"]
    AW --> SA
    SA --> RA["Raw Artifact Store"]
    RA --> RN["Research Normalizer"]
    RN --> RS["Research Submission"]
    RS --> GD["Grader DAG"]
    GD --> SS["Score Store"]
    SS --> RR["Research Report"]
```

### 4.1 分层职责

| 层 | 职责 | 禁止事项 |
|---|---|---|
| Core | Run、Case、Attempt、状态机、租约、Artifact、评分 DAG | 不包含豆包文案或 xbench 特例 |
| Research Domain | Research Schema、Track、Normalizer、Citation、报告 | 不直接操作具体产品 UI |
| Benchmark Adapter | 读取数据、构建输入、包装官方评分器 | 不启动浏览器或调用产品 |
| SUT Adapter | 调用网页/API/Agent 并采集原始结果 | 不读取 gold，不计算 Benchmark 分数 |
| Grader | 基于冻结产物生成版本化 ScoreRecord | 不修改原始回答 |

## 5. 目标目录结构

在现有仓库上增量建设以下结构：

```text
src/
├── cli/
│   ├── trueeval.ts
│   └── doubao.ts                       # 保留为单题调试入口
├── core/
│   ├── config/
│   ├── orchestrator/
│   ├── scheduler/
│   ├── state/
│   ├── storage/
│   ├── workers/
│   └── grading/
├── domains/
│   └── research/
│       ├── contracts/
│       ├── normalizers/
│       ├── tracks/
│       │   ├── short-fact/
│       │   └── long-form/
│       ├── citations/
│       ├── evidence/
│       └── reporting/
├── adapters/
│   ├── benchmark/
│   │   ├── jsonl/
│   │   ├── xbench-deepsearch/
│   │   ├── deepresearcheval/
│   │   └── browsecomp-zh/
│   └── sut/
│       ├── process/
│       ├── api/
│       └── web/doubao/
└── schemas/
    └── generated/                      # Zod 导出的 JSON Schema

grader-runtime/
├── pyproject.toml
├── trueeval_graders/
│   ├── protocol.py
│   ├── official/
│   ├── citation/
│   └── long_form/
└── tests/

tests/
├── fixtures/
├── unit/
├── contract/
├── integration/
└── live/                               # 默认 CI 不执行
```

不要立即删除 `src/cli/doubao.ts`。统一工作流稳定前，它继续作为 Adapter 的人工调试入口。

## 6. Canonical Contracts

所有 Contract 使用 Zod 定义，以 Zod 为运行时事实来源，并导出 JSON Schema。Schema 必须带 `schema_version`；破坏性修改必须升级版本。

### 6.1 TaskSpec

```ts
type ResearchTrack = "short_fact" | "long_form";

interface TaskSpec {
  schema_version: "trueeval.task.v0.1";
  task_id: string;
  benchmark_id: string;
  split: string;
  domain: "research";
  track: ResearchTrack;
  input: {
    prompt: string;
    language: string;
    as_of: string | null;
    attachments: ArtifactRef[];
  };
  expected_output: {
    answer_form: "short_text" | "list" | "structured_json" | "report";
    citation_required: boolean;
  };
  required_capabilities: string[];
  constraints: {
    timeout_seconds: number;
    internet_required: boolean;
    max_attempts: number;
  };
  evaluation_profile: {
    official_grader: string | null;
    overlays: Array<"citation_reliability">;
  };
  provenance: Record<string, unknown>;
}
```

运行阶段只能向 SUT 传递 `input` 和允许公开的约束。`gold.jsonl`、评分关键词、参考答案和参考 URL 不得进入 `TaskSpec` 的 SUT 请求对象。

### 6.2 SUTSpec

```ts
interface SUTSpec {
  schema_version: "trueeval.sut.v0.1";
  sut_id: string;
  provider: string;
  product: string;
  channel: "web" | "api" | "process" | "manual";
  adapter_id: string;
  adapter_version: string;
  account_tier: string | null;
  capabilities: {
    research_mode: boolean;
    short_fact: boolean;
    long_form: boolean;
    visible_citations: boolean;
    citation_urls: "full" | "visible_only" | "none";
    file_output: boolean;
  };
  concurrency: {
    max_workers: number;
    account_scoped: boolean;
  };
}
```

同一品牌的 Web 和 API 必须使用不同 `sut_id`。

### 6.3 RunManifest

```yaml
schema_version: trueeval.run_manifest.v0.1
run_id: null
name: doubao-xbench-2505-smoke
benchmark:
  id: xbench-deepsearch
  version: 17c562192cc7e62215bfb98b65e9f8806fb95504
  split: "2505"
  task_selector:
    ids: []
    limit: 5
    seed: 20260819
sut:
  id: doubao.web.deep-research
execution:
  worker: browser
  concurrency: 1
  max_attempts: 1
  headless: false
  keep_worker_open: true
  new_session_per_task: true
  timeout_seconds: 900
evaluation:
  run_official: true
  overlays: [citation_reliability]
  grader_versions_locked: true
artifacts:
  root: artifacts/runs
  retain_raw_html: true
  retain_screenshots: true
```

执行开始时生成 `manifest.lock.json`，写入：

- 最终 `run_id`；
- Benchmark commit 和输入文件 SHA-256；
- Git commit；
- Adapter 版本；
- Node、Python、Playwright、Chrome 版本；
- 操作系统、语言、时区；
- Judge 名称、版本、参数和 Prompt 哈希；
- 任务稳定 ID 列表及顺序。

锁定后不得原地修改。配置变化必须创建新 Run。

### 6.4 RawSUTResult

```ts
interface RawSUTResult {
  schema_version: "trueeval.raw_sut_result.v0.1";
  run_id: string;
  case_id: string;
  attempt_id: string;
  task_id: string;
  sut_id: string;
  status: ExecutionStatus;
  submitted_at: string | null;
  completed_at: string | null;
  raw_answer_text: string | null;
  raw_citations: unknown[];
  raw_response: ArtifactRef | null;
  screenshots: ArtifactRef[];
  events: ArtifactRef;
  usage: {
    latency_ms: number;
    input_tokens: number | null;
    output_tokens: number | null;
    search_calls: number | null;
    cost_usd: number | null;
  };
  collection: {
    answer_status: "complete" | "partial" | "not_observable";
    citation_status: "collected" | "product_absent" | "adapter_failed" | "not_observable";
  };
  error: ErrorRecord | null;
}
```

### 6.5 ResearchSubmission

```ts
interface ResearchSubmission {
  schema_version: "trueeval.research_submission.v0.1";
  run_id: string;
  case_id: string;
  attempt_id: string;
  task_id: string;
  track: "short_fact" | "long_form";
  final_answer: string;
  sections: Array<{
    section_id: string;
    heading: string | null;
    text: string;
  }>;
  claims: ClaimRecord[];
  citations: CitationRecord[];
  attachments: ArtifactRef[];
  normalization: {
    normalizer_id: string;
    normalizer_version: string;
    source_artifact_sha256: string;
  };
}
```

Normalizer 只能从冻结的 RawSUTResult 和 Artifact 派生 Submission，不得补写产品没有输出的事实或引用。

### 6.6 CitationRecord 与 EvidenceSnapshot

```ts
interface CitationRecord {
  citation_id: string;
  display_text: string | null;
  visible_url: string | null;
  resolved_url: string | null;
  quoted_text: string | null;
  claim_ids: string[];
  collection_status:
    | "resolved"
    | "visible_only"
    | "product_absent"
    | "adapter_failed"
    | "unresolvable";
}

interface EvidenceSnapshot {
  schema_version: "trueeval.evidence_snapshot.v0.1";
  evidence_id: string;
  citation_id: string;
  requested_url: string;
  resolved_url: string | null;
  retrieved_at: string;
  status: "fetched" | "paywalled" | "login_required" | "blocked" | "not_found" | "error";
  http_status: number | null;
  title: string | null;
  publisher: string | null;
  published_at: string | null;
  text_artifact: ArtifactRef | null;
  html_artifact: ArtifactRef | null;
  sha256: string | null;
}
```

### 6.7 ScoreRecord

```ts
interface ScoreRecord {
  schema_version: "trueeval.score.v0.1";
  run_id: string;
  case_id: string;
  attempt_id: string;
  task_id: string;
  namespace: "official" | "trueeval";
  metric_id: string;
  role: "gate" | "score" | "diagnostic";
  value: number | string | boolean | null;
  status: "scored" | "failed" | "not_observable" | "not_applicable";
  grader: {
    id: string;
    version: string;
    config_hash: string;
  };
  evidence_refs: ArtifactRef[];
  detail: Record<string, unknown>;
}
```

## 7. Adapter SDK

### 7.1 BenchmarkAdapter

```ts
interface BenchmarkAdapter {
  spec(): Promise<BenchmarkSpec>;
  listTasks(split: string): AsyncIterable<TaskSpec>;
  loadGold(taskId: string, gradeToken: GradeAccessToken): Promise<GoldRecord>;
  createOfficialGradeJob(input: OfficialGradeInput): Promise<GraderJob | null>;
}
```

约束：

- `listTasks()` 不得打开 `gold.jsonl`；
- `loadGold()` 只能在独立 Grade Command 中调用；
- Task ID 必须稳定，不能使用当前读取行号；
- 官方代码通过薄包装调用，不复制或重新解释其评分语义；
- 上游依赖应运行在独立 Python venv，后续可升级为 Docker。

首期可先实现一个通用 JSONL Adapter，再为三套 Benchmark 增加配置和官方 Grader 包装。

### 7.2 SUTAdapter

```ts
interface SUTAdapter {
  spec(): Promise<SUTSpec>;
  openWorker(ctx: WorkerContext): Promise<WorkerHandle>;
  probe(worker: WorkerHandle): Promise<ProbeResult>;
  startSession(worker: WorkerHandle, ctx: CaseContext): Promise<SessionHandle>;
  submit(session: SessionHandle, request: SUTRequest): Promise<SubmissionHandle>;
  observe(submission: SubmissionHandle): Promise<Observation>;
  collect(submission: SubmissionHandle): Promise<RawSUTResult>;
  recover(worker: WorkerHandle, checkpoint: Checkpoint): Promise<RecoveryResult>;
  closeSession(session: SessionHandle): Promise<void>;
  closeWorker(worker: WorkerHandle): Promise<void>;
}
```

豆包现有实现的迁移方式：

| 现有方法 | 新接口 |
|---|---|
| `open()`、`ensureLogin()` | `openWorker()` + `probe()` |
| `startCleanConversation()`、`selectResearchMode()` | `startSession()` |
| `submitPrompt()` | `submit()` |
| `waitForCompletion()` 内部轮询 | `observe()` |
| `collect()` | `collect()` |

先增加 Facade 包装现有 `DoubaoWebAdapter`，不要第一步就重写其页面定位逻辑。

### 7.3 外部 Agent 自动化脚本协议

为了接入 Python Agent、第三方 API Wrapper 或独立脚本，MVP 支持 Process Adapter：

```yaml
adapter_id: example.process.research-agent
transport: process
command:
  - python3
  - agents/example/run.py
timeout_seconds: 1800
capabilities:
  short_fact: true
  long_form: true
  citations: full
```

Core 使用参数数组直接启动进程，不通过 shell 拼接字符串：

```text
python3 agents/example/run.py \
  --request <absolute-request-json> \
  --result-dir <absolute-result-directory>
```

脚本必须：

1. 只读取 `request.json`；
2. 将原始响应写入自己的 result directory；
3. 原子写入 `result.raw.json.tmp`，完成后 rename 为 `result.raw.json`；
4. 输出符合 RawSUTResult Schema 的结果；
5. 不读取 Benchmark 目录中的 gold；
6. 退出码只表示协议是否执行成功，产品拒答等业务状态写入结果；
7. 不把 API Key、Cookie 或环境变量写入 Artifact。

Process Adapter 让不同语言的自动化脚本接入 TrueEval，而不要求全部重写为 TypeScript。

## 8. 运行状态机

### 8.1 Run、Case、Attempt

```text
Run
└── Case（一个 Task × 一个 SUT）
    └── Attempt（一次实际生成）
```

- Run：冻结的一次评测配置；
- Case：一道题在一个被测产品上的逻辑评测单元；
- Attempt：一次不可覆盖的产品调用；
- Retry 只有在确认未提交时才能复用 Attempt；重新生成必须创建新 Attempt。

### 8.2 Case 状态

```text
CREATED
→ QUEUED
→ RESOURCE_LEASED
→ WORKER_READY
→ SESSION_CREATED
→ SUBMITTING
→ SUBMITTED
→ RUNNING
→ COMPLETED
→ COLLECTED
→ NORMALIZED
→ READY_FOR_GRADING
→ GRADING
→ SCORED
→ DONE
```

终止或人工状态：

```text
NEEDS_LOGIN
NEEDS_HUMAN_VERIFICATION
CAPABILITY_MISMATCH
UI_CHANGED
SUBMISSION_UNCONFIRMED
PROVIDER_ERROR
TIMED_OUT
COLLECTION_FAILED
NORMALIZATION_FAILED
GRADING_FAILED
CANCELLED
```

每次状态转换必须先写 Event，再更新 SQLite 当前状态。Event 使用单调递增 `seq`，不得原地修改。

### 8.3 Retry 规则

| 情况 | 行为 |
|---|---|
| 打开页面失败且尚未提交 | 允许 Transport Retry |
| API 明确返回未创建任务 | 允许 Transport Retry |
| 已获得 external job/session ID | 只允许 Recovery |
| 点击发送后无法判断是否成功 | `SUBMISSION_UNCONFIRMED`，禁止自动重发 |
| 产品完成但采集失败 | 从冻结 HTML/API Response 重新 Collect |
| 评分失败 | 只重跑 Grader，不重新调用产品 |
| 用户要求重新生成 | 创建新 Attempt，并单独统计 |

## 9. 具体执行工作流

### 9.1 创建 Run

```text
读取 Manifest
→ Schema 校验
→ 解析 Benchmark 与 SUT
→ Capability 检查
→ 选题并冻结顺序
→ 计算输入哈希
→ 生成 manifest.lock.json
→ 创建 SQLite Run/Case 记录
```

任何能力不匹配都必须在调用产品前失败。例如长文任务不能分配给 `long_form=false` 的产品模式。

### 9.2 执行 Case

```text
领取 Case Lease
→ 获取或创建 Worker
→ 创建全新产品会话
→ 校验空白会话和目标模式
→ 构建仅包含公开字段的 SUTRequest
→ 写 request.json
→ 提交并确认
→ 定时 observe
→ 达到完成条件
→ collect 原始产物
→ 校验 RawSUTResult
→ 写 completion marker
→ 释放 Case Lease
```

Browser Worker 在同一个 Batch 中保持 Chrome 打开并复用登录态；每道题必须调用 `startSession()` 创建新对话。正式 Web Run 默认 `headless=false`、`concurrency=1`。

### 9.3 Normalize

```text
读取冻结 RawSUTResult
→ 校验执行完成
→ 解析最终正文
→ 解析章节
→ 提取产品展示的引用
→ 生成 CitationRecord
→ 可选运行 Claim Extractor
→ 写 ResearchSubmission
```

Claim Extractor 的输出必须标记为派生数据。提取失败不允许修改原始回答，也不允许凭空添加引用。

### 9.4 Grade

Grade 必须是独立命令和独立进程边界：

```text
读取 ResearchSubmission
→ 获取 GradeAccessToken
→ 加载 gold
→ 执行官方 Grader
→ 根据 Overlay 获取 Evidence Snapshot
→ 执行 Citation Graders
→ 写 ScoreRecord
→ 聚合 Run Report
```

执行 Worker 不得获得 `GradeAccessToken`。

## 10. 三条评分管线

### 10.1 Short Fact

```text
Execution Gate
→ Answer Contract Validation
→ Official Answer Grader
→ Temporal Validity（如适用）
→ Citation Overlay（如启用）
```

主指标保持官方口径：

- xbench：`official.answer_accuracy`；
- BrowseComp-ZH：`official.answer_accuracy`；
- BrowseComp-ZH 的 ECE 作为单独诊断项。

引用分不能改变官方答案准确率。

### 10.2 Long Form

```text
Execution Gate
→ Report Contract Validation
→ Official Quality Grader
→ Official Fact Grader
→ Claim Extraction
→ Citation Overlay
```

DeepResearchEval 必须分别保存：

- `official.quality_score`；
- `official.fact_ratio`；
- TrueEval 引用诊断指标。

不生成不可解释的加权总分。

### 10.3 Citation Reliability Overlay

评分 DAG：

```text
Citation Extraction
├── URL Resolution → Link Validity
├── Evidence Fetch → Evidence Snapshot
├── Claim-Citation Mapping
│   └── Claim-Evidence Entailment
├── Source Classification → Source Quality
└── Evidence Date Parsing → Temporal Validity
```

首期指标：

| Metric | 计算对象 | 缺失策略 |
|---|---|---|
| `trueeval.citation_validity` | 引用 URL 是否可解析 | 产品未提供引用时按任务要求处理 |
| `trueeval.citation_correctness` | 被引用来源是否支持对应主张 | 无证据正文则 `not_observable` |
| `trueeval.citation_completeness` | 重要可验证主张的支持覆盖率 | 明确要求引用且产品无引用时为 0 |
| `trueeval.source_quality` | 原始来源、权威性、相关性 | 无法识别来源时 `not_observable` |
| `trueeval.temporal_validity` | 来源日期符合 `as_of` | 非时效题 `not_applicable` |

产品没有引用和 Adapter 提取失败必须区分：

- `product_absent`：产品能力结果，可参与完整性评分；
- `adapter_failed`：系统失败，不得记成产品 0 分；
- `not_observable`：渠道本身不暴露引用，报告中明确披露。

Evidence Fetcher 必须保存 URL、重定向链、抓取时间、状态、正文快照和 SHA-256。登录墙、付费墙和 robots 限制记录状态，不采取绕过措施。

### 10.4 Judge 子系统定位

TrueEval 不设置一个能够任意读取全部数据并输出总分的“万能 Judge”。Judge 是 Grader DAG 中需要语义判断的受控节点；确定性检查和官方评分器仍然优先。

```text
能确定性判断
→ 使用程序 Grader

Benchmark 已提供官方评分器
→ 包装并运行官方 Grader

必须理解语义、主张或证据
→ 使用版本化 LLM Judge

Judge 低置信度或互相冲突
→ 第二 Judge / Adjudicator / 人工复核
```

Judge 只允许承担：

- Claim Extraction；
- Claim-Citation Mapping；
- Claim-Evidence Entailment；
- 非官方长文质量维度；
- 无法由元数据确定的来源类型识别；
- 证据冲突和证据不足分类。

Judge 不得承担：

- 任务调度、重试和状态转换；
- URL 可访问性、时间比较和文件完整性等确定性工作；
- 替代现有官方评分器；
- 生成不可解释的跨 Track 总分；
- 修正或补全被测产品的答案；
- 根据产品品牌、价格或历史排名调整评分。

### 10.5 Judge DAG

```mermaid
flowchart TD
    RS["Research Submission"] --> EV["Execution / Artifact Validation"]
    EV --> OG["Official Benchmark Grader"]
    EV --> CE["Claim Extractor"]
    EV --> LQ["Long-form Quality Judge"]
    CE --> CM["Claim-Citation Mapper"]
    CM --> ER["Evidence Resolver"]
    ER --> EN["Entailment Judge"]
    ER --> SQ["Source Quality Grader"]
    ER --> TV["Temporal Validity Grader"]
    OG --> SC["ScoreRecord Store"]
    LQ --> SC
    EN --> SC
    SQ --> SC
    TV --> SC
    SC --> CF{"冲突或低置信度?"}
    CF -->|是| AD["Adjudication"]
    CF -->|否| AG["Track Aggregation"]
    AD --> AG
```

长文不能只调用一次全局 Judge。事实和引用按 Claim 局部评分；只有任务覆盖度、结构、论证连贯性等全局维度允许读取完整报告。

### 10.6 JudgeJob Contract

每次 Judge 调用必须生成不可变 JudgeJob：

```ts
interface JudgeJob {
  schema_version: "trueeval.judge_job.v0.1";
  judge_job_id: string;
  run_id: string;
  case_id: string;
  attempt_id: string;
  grader_id: string;
  grader_version: string;
  purpose:
    | "claim_extraction"
    | "claim_citation_mapping"
    | "citation_entailment"
    | "long_form_quality"
    | "source_classification"
    | "adjudication";
  input_refs: ArtifactRef[];
  allowed_input_fields: string[];
  judge_config: {
    provider: string;
    model: string;
    model_version: string | null;
    temperature: number;
    seed: number | null;
    max_output_tokens: number;
    prompt_id: string;
    prompt_version: string;
    prompt_sha256: string;
    output_schema: string;
  };
  cache_key: string;
  cache_source_job_id: string | null;
  created_at: string;
}
```

Judge Provider 使用统一接口，具体模型 SDK 不得泄漏到业务 Grader：

```ts
interface JudgeProvider {
  providerId(): string;
  invoke(
    job: JudgeJob,
    input: Readonly<Record<string, unknown>>,
    signal: AbortSignal,
  ): Promise<{
    actual_model: string | null;
    raw_response: unknown;
    usage: {
      input_tokens: number | null;
      output_tokens: number | null;
      cost_usd: number | null;
    };
  }>;
}
```

网络错误、Rate Limit 和输出 Schema 错误必须使用不同错误码。协议重试次数由 Judge Profile 限制，不能通过反复调用挑选对产品更有利的判决。

Judge 模型不硬编码在 Grader 中，通过版本化 Judge Profile 注入：

```yaml
judge_profile_id: citation-primary-v1
provider: configurable
model: configurable
temperature: 0
seed: 20260819
max_output_tokens: 1200
prompt:
  id: citation-entailment
  version: v1
output_schema: trueeval.citation_verdict.v0.1
reliability:
  confidence_threshold: 0.75
  second_judge_profile: citation-secondary-v1
  adjudicator_profile: citation-adjudicator-v1
```

正式 Run 必须将实际 Provider、模型、参数、Prompt 哈希和 Profile 哈希写入 `manifest.lock.json`。即使 Provider 使用滚动模型别名，也必须记录 API 返回的实际模型标识；无法获得时明确写 `null`。

### 10.7 结构化判决

Judge 只允许输出符合 JSON Schema 的结构化结果。不得依赖自由文本中解析出的数字。

Citation Entailment 输出：

```ts
interface CitationVerdict {
  schema_version: "trueeval.citation_verdict.v0.1";
  claim_id: string;
  citation_id: string;
  verdict:
    | "supported"
    | "partially_supported"
    | "contradicted"
    | "irrelevant"
    | "insufficient_evidence"
    | "evidence_unavailable";
  score: number | null;
  confidence: number;
  evidence_spans: Array<{
    artifact_id: string;
    start: number;
    end: number;
  }>;
  rationale: string;
  flags: string[];
}
```

默认分值映射由 Grader 配置完成，不由 Judge 自行决定：

| Verdict | 默认值 | 说明 |
|---|---:|---|
| `supported` | 1.0 | 证据直接支持完整主张 |
| `partially_supported` | 0.5 | 只支持主张的一部分 |
| `contradicted` | 0.0 | 证据与主张冲突 |
| `irrelevant` | 0.0 | 来源存在但不支持该主张 |
| `insufficient_evidence` | null | 当前证据无法判定 |
| `evidence_unavailable` | null | 无法获得证据正文 |

`null` 的聚合策略必须由 Rubric 明确指定，不得静默转换为 0。Judge 不输出完整思维链，只保存简短理由、证据字符区间和结构化结论。

### 10.8 Claim Extractor 约束

Claim Extractor 是派生数据处理器，不是评分器。每条 Claim 必须映射回答案原文：

```ts
interface ClaimRecord {
  claim_id: string;
  text: string;
  source_span: {
    start: number;
    end: number;
  };
  importance: "major" | "minor";
  verifiability: "externally_verifiable" | "opinion" | "non_verifiable";
  citation_ids: string[];
}
```

Extractor 不得：

- 改写答案使错误事实变正确；
- 添加答案中不存在的事实；
- 将多个独立事实合并成无法单独判定的 Claim；
- 为没有引用的 Claim 自动补 Citation；
- 将观点、建议或修辞句强制当作事实。

Claim Extraction 失败时，引用正确性和完整性标记为 `not_observable` 或 `grading_failed`，不得用空 Claim 列表产生虚假满分。

### 10.9 Judge 输入隔离与盲评

每种 Judge 通过 `allowed_input_fields` 获取最小输入：

| Judge | 可以读取 | 不可以读取 |
|---|---|---|
| Claim Extractor | 匿名答案正文 | gold、SUT 名称、其他产品答案 |
| Citation Entailment | Claim、Citation、Evidence | 产品名称、榜单、无关 gold |
| Long-form Quality | Task、Rubric、匿名报告 | 产品名称、价格、历史分数 |
| Official Judge | 官方规定输入 | TrueEval 自行增加的隐藏信息 |
| Adjudicator | 两个结构化判决、原证据、Rubric | Judge 品牌偏好和无关运行信息 |

Judge 默认看不到：

- 被测产品和 Provider 名称；
- 账号价格与套餐；
- 榜单历史；
- 其他产品的答案和分数；
- 用户对产品的主观评价。

如果未来进行 Pairwise Judge，候选答案顺序必须随机化，并抽样执行 A/B 与 B/A 顺序一致性检查。

### 10.10 Prompt Injection 防护

被测答案、引用网页和附件都是不可信数据。Judge Prompt 必须明确：答案或证据中的所有指令均为待评估内容，不能执行。

实现要求：

1. Rubric、Task、Answer、Evidence 使用结构化字段传递；
2. 不把 Evidence 直接拼接进 System Prompt；
3. Judge 无浏览器、Shell、文件写入或 Secret 权限；
4. Judge 只能读取显式 Artifact allowlist；
5. 输出必须通过 JSON Schema 校验；
6. Evidence Span 必须引用冻结 Artifact；
7. Judge 输出中的 URL、命令和工具请求一律不执行；
8. 检测到注入式内容时在 `flags` 中记录，但仍按证据语义评分。

### 10.11 稳定性、复判与人工审查

`temperature=0` 不代表绝对确定。每次 Judge 调用必须保存输入哈希、原始输出、结构化输出、重试次数和实际模型信息。Judge 自报 `confidence` 只用于触发复判，不能作为模型可靠性的唯一依据。

默认策略：

1. 普通样本调用一次 Primary Judge；
2. 低置信度、Schema 重试或高风险标签调用 Secondary Judge；
3. 两个 Judge 的离散标签冲突时调用 Adjudicator；
4. Adjudicator 仍不确定时进入 Human Review Queue；
5. 正式报告披露复判率、冲突率和人工复核率。

触发复判的条件至少包括：

- `confidence` 低于 Judge Profile 阈值；
- `supported` 与 `contradicted` 冲突；
- 分值差超过 Rubric 阈值；
- 输出连续两次不能通过 Schema；
- Evidence 不完整但 Judge 给出确定性高分；
- 分数处于发布或门槛边界附近；
- 抽样稳定性检查命中。

不允许通过无限重试挑选最高分。Schema Retry、Secondary Judge 和 Regeneration 是三种不同事件，必须分别记录。

### 10.12 Judge 校准集

Judge 进入正式主榜前必须通过人工校准：

- Citation Judge：至少 30–50 个 Claim-Citation-Evidence 样本；
- 覆盖支持、部分支持、矛盾、无关、证据不足和证据不可用；
- 同时包含中文、英文、短文本和长文本；
- 至少两名人工标注者独立标注，分歧样本经过裁决；
- 校准集与正式测试集隔离，不用于被测 Agent 提示。

至少报告：

- Accuracy；
- Macro-F1；
- Cohen's Kappa；
- 各标签混淆矩阵；
- 中文与英文分组表现；
- Primary/Secondary 冲突率。

如果 Judge 未达到 Rubric 预设的一致性阈值，其结果只能作为实验性诊断项，不能成为正式主榜指标。

### 10.13 Judge 缓存与成本控制

相同输入和相同 Judge 配置不得重复付费调用。缓存键：

```text
grader_id
+ grader_version
+ judge_profile_hash
+ task_hash
+ answer_hash
+ evidence_hash
+ output_schema_version
```

缓存命中必须复用完整 Judge Verdict Artifact，而不是只复用最终数字。

成本控制顺序：

1. 确定性节点不调用 LLM；
2. 同一答案只做一次 Claim Extraction；
3. 同一规范化 URL 只抓取一次 Evidence Snapshot；
4. Claim-Evidence 对按哈希缓存；
5. 只有冲突或低置信度样本调用 Secondary；
6. 报告重新生成不触发 Judge；
7. Judge Profile 改变时创建新 ScoreRecord，不覆盖旧分数。

### 10.14 Judge Artifact 与审计

每个 JudgeJob 保存：

```text
judge-jobs/<judge-job-id>/
├── job.json
├── prompt.metadata.json
├── input.refs.json
├── response.raw.json
├── verdict.json
├── validation.json
└── usage.json
```

`prompt.metadata.json` 保存 Prompt ID、版本和 SHA-256；正式环境可以不在公开 Artifact 中暴露私有 Judge Prompt 全文，但必须在受控内部存储中可复现。

### 10.15 Judge 验收标准

Judge 子系统完成需要同时满足：

1. Judge Provider、模型和 Prompt 不硬编码在评分器中；
2. 所有输出均通过版本化 JSON Schema；
3. Judge 无法读取未授权 Artifact 和 SUT Secret；
4. 产品身份默认对 Judge 隐藏；
5. Claim 可以映射回答案原文字符区间；
6. Citation Verdict 可以映射到具体 Evidence Span；
7. Schema Retry、Secondary、Adjudication 和 Human Review 分开记录；
8. 相同输入与配置可以命中缓存；
9. 更换 Judge Profile 不需要重新调用 SUT；
10. 校准报告包含人工一致性和混淆矩阵；
11. Judge 失败不会被计为产品内容 0 分；
12. 官方指标和 TrueEval Judge 指标保持不同命名空间。

## 11. Artifact 布局

```text
artifacts/runs/<run_id>/
├── manifest.input.yaml
├── manifest.lock.json
├── events.jsonl
├── run-summary.json
├── report.json
├── report.md
└── cases/<safe-task-id>/
    ├── case.json
    └── attempts/0001/
        ├── request.json
        ├── events.jsonl
        ├── checkpoint.json
        ├── raw/
        │   ├── result.raw.json
        │   ├── response.html
        │   ├── response.txt
        │   ├── citations.raw.json
        │   └── screenshots/
        ├── normalized/
        │   └── research-submission.json
        ├── evidence/
        │   └── <evidence-id>/
        │       ├── metadata.json
        │       ├── page.html
        │       └── page.txt
        ├── judge-jobs/
        │   └── <judge-job-id>/
        │       ├── job.json
        │       ├── input.refs.json
        │       ├── response.raw.json
        │       └── verdict.json
        └── scores/
            └── <grader-id>.json
```

所有 ArtifactRef 使用相对 Run 根目录的路径、媒体类型、字节数和 SHA-256。数据库保存索引，不把大段 HTML 放进 SQLite。

Artifact 写入协议：

1. 写临时文件；
2. `fsync` 或关闭文件；
3. 计算 SHA-256；
4. 原子 rename；
5. 写 Artifact 元数据；
6. 最后更新数据库状态。

## 12. SQLite 最小模型

MVP 使用 `.trueeval/state.db`。至少包含：

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  manifest_uri TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE cases (
  case_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  sut_id TEXT NOT NULL,
  status TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  current_attempt_id TEXT,
  lease_owner TEXT,
  lease_expires_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(run_id, task_id, sut_id),
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE attempts (
  attempt_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  external_session_id TEXT,
  submitted_at TEXT,
  completed_at TEXT,
  result_uri TEXT,
  error_code TEXT,
  UNIQUE(case_id, attempt_number),
  FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  case_id TEXT,
  attempt_id TEXT,
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  case_id TEXT,
  attempt_id TEXT,
  kind TEXT NOT NULL,
  uri TEXT NOT NULL,
  media_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE scores (
  score_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  metric_id TEXT NOT NULL,
  grader_id TEXT NOT NULL,
  grader_version TEXT NOT NULL,
  status TEXT NOT NULL,
  value_json TEXT,
  record_uri TEXT NOT NULL,
  UNIQUE(attempt_id, metric_id, grader_id, grader_version)
);

CREATE TABLE judge_jobs (
  judge_job_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  grader_id TEXT NOT NULL,
  grader_version TEXT NOT NULL,
  purpose TEXT NOT NULL,
  profile_hash TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL,
  cache_source_job_id TEXT,
  job_uri TEXT NOT NULL,
  verdict_uri TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX idx_judge_jobs_cache
ON judge_jobs(cache_key, status);
```

数据库启动时启用 WAL、foreign keys 和 busy timeout。Schema 迁移必须版本化，不在运行时静默删除列或表。

## 13. CLI 设计

统一入口：

```bash
# 校验配置和能力，不调用产品
npm run trueeval -- validate --manifest manifests/doubao-xbench-smoke.yaml

# 创建并执行 Run；默认只读 tasks，不读取 gold
npm run trueeval -- run --manifest manifests/doubao-xbench-smoke.yaml

# 恢复中断 Run，不重复提交已确认任务
npm run trueeval -- resume --run-id <run-id>

# 只对冻结结果评分
npm run trueeval -- grade --run-id <run-id>

# 更换 Grader 版本重新评分
npm run trueeval -- grade --run-id <run-id> --profile citation-v2

# 生成 JSON 和 Markdown 报告
npm run trueeval -- report --run-id <run-id>

# 查看失败和需要人工处理的 Case
npm run trueeval -- status --run-id <run-id>
```

退出码：

| 退出码 | 含义 |
|---:|---|
| 0 | 命令成功；Run 中可以存在内容低分 |
| 2 | 配置或 Schema 错误 |
| 3 | 需要人工登录/验证 |
| 4 | 部分 Case 系统失败 |
| 5 | Grader 失败 |
| 10 | 意外内部错误 |

不要使用“所有产品答案都正确”作为 CLI 成功条件。

## 14. Benchmark 接入规则

### 14.1 xbench-DeepSearch

- 首轮只运行 `2505`；
- 首次 smoke test 固定 5 题 ID，不依赖随机读取顺序；
- 执行阶段使用本地解密 `tasks.jsonl`；
- `gold.jsonl` 只允许 Grade Command 读取；
- 使用官方答案评分器；
- Citation Overlay 是 TrueEval 诊断项，不改变官方分。

### 14.2 DeepResearchEval

- 先用 v1 的 2–3 题验证 30 分钟级任务；
- 保留官方 quality 和 fact 两条评分管线；
- v2 动态题必须冻结 `as_of`；
- 报告正文和附件均作为 Artifact；
- Citation Overlay 在能观察到 URL 时运行。

### 14.3 BrowseComp-ZH

- 用作中文复杂短事实补充验证；
- 不提交受保护明文；
- 不作为当前正式公开中文榜单；
- 答案准确率与 ECE 分开保存。

### 14.4 新 Benchmark 接入检查表

- [ ] 已固定上游 repo、commit、路径、license 和 SHA-256；
- [ ] 已定义稳定 task ID；
- [ ] tasks 与 gold 物理分离；
- [ ] 已声明 Track 和 Output Contract；
- [ ] 已包装官方评分器；
- [ ] 已记录聚合方式与缺失策略；
- [ ] 动态题包含 `as_of` 或快照；
- [ ] Contract Test 通过；
- [ ] 不把待测产品生成的数据写回 gold。

## 15. SUT 接入规则

每个新 Agent、API 或网页产品需要提供：

```text
adapter manifest
SUTSpec
capability probe
session isolation implementation
submission confirmation
completion detection
raw result collector
error mapping
contract tests
live smoke test instructions
```

### Web Adapter 必须满足

- 正式运行使用可见浏览器；
- 持久化 Profile 只存本机；
- 一题一新会话；
- 提交前核对 Prompt 原文；
- 提交不确定时不自动重发；
- 完成判断不能只依赖固定 sleep；
- UI 控件不唯一时显式 `UI_CHANGED`；
- 保存完成截图、HTML 和可见正文；
- 不导出 Cookie、二维码或个人信息。

### API/Agent Adapter 必须满足

- 保存去敏后的原始 request/response；
- 记录模型、endpoint、参数和工具配置；
- 异步任务保存 external job ID；
- 支持按 job ID 恢复；
- 区分 rate limit、provider error、policy refusal 和 timeout；
- 能观测的 token、成本、搜索次数如实记录，不能估算后冒充真实值。

## 16. 报告协议

报告分三层：

### 16.1 Case Report

- Task、SUT、Attempt 和状态；
- 原始回答链接；
- 官方分；
- TrueEval 诊断分；
- 引用与证据明细；
- 系统错误和人工处理记录。

### 16.2 Track Summary

Short Fact：

- execution success rate；
- official answer accuracy；
- 系统失败数；
- 引用指标分布；
- latency 的 median、p90。

Long Form：

- execution success rate；
- official quality score；
- official fact ratio；
- 引用指标分布；
- latency 的 median、p90。

### 16.3 Research Capability Vector

```json
{
  "execution_success_rate": 0.0,
  "short_fact_accuracy": 0.0,
  "long_form_quality": 0.0,
  "long_form_fact_ratio": 0.0,
  "citation_validity": 0.0,
  "citation_correctness": 0.0,
  "citation_completeness": 0.0,
  "source_quality": 0.0,
  "temporal_validity": 0.0
}
```

不可观测项保持 `null` 并附原因，不能用 0 填充。MVP 不生成跨 Track 总分。

## 17. 测试策略

### 17.1 Unit Tests

- Schema 成功与失败样例；
- 状态转换合法性；
- Task selector 稳定性；
- URL 规范化和去重；
- Artifact SHA-256；
- 错误码映射；
- 聚合时 `null/not_observable/system_failure` 的处理。
- Judge Cache Key、Verdict 映射和复判触发条件。

### 17.2 Contract Tests

- 三个 Benchmark 的 tasks 均可解析为 TaskSpec；
- gold 无法通过执行阶段 API 读取；
- 豆包 Facade 输出符合 RawSUTResult；
- Process Adapter fixture 可以接收请求并返回结果；
- 官方 Grader Wrapper 输出符合 ScoreRecord；
- Fake Judge 输出符合 JudgeJob 和 Verdict Schema；
- Judge 只能读取 allowlist 中的 Artifact；
- 旧版或未知 Schema 被明确拒绝。

### 17.3 Integration Tests

使用本地 Fake SUT，不连接真实产品：

1. 五题 Batch 全部完成；
2. 第三题超时，其余任务继续；
3. 进程在 `SUBMITTED` 后退出，恢复时不重复提交；
4. 评分失败后只重跑 Grader；
5. Adapter 返回无引用、坏链接和提取失败三种情况；
6. 相同冻结结果重复评分得到相同确定性分数。
7. Primary 与 Secondary 冲突时创建 Adjudication Job；
8. 相同 Judge 输入和配置命中缓存，不重复调用 Provider。

### 17.4 Live Tests

默认 CI 不运行，需要显式环境变量和本地账号：

- 豆包 probe；
- 豆包单题 short fact；
- 豆包单题 long form；
- 豆包连续五题、每题新会话；
- 人工中断后恢复；
- 引用组件 URL 提取。

Live Test 不得保存或上传浏览器 Profile。

## 18. 可观测性与错误分类

日志使用结构化 JSON，不把整篇回答重复写入控制台。至少包含：

```json
{
  "timestamp": "ISO-8601",
  "level": "info",
  "run_id": "...",
  "case_id": "...",
  "attempt_id": "...",
  "component": "browser-worker",
  "event": "SUBMITTED",
  "detail": {}
}
```

错误分三类汇总：

| 类型 | 示例 | 是否计内容 0 分 |
|---|---|---|
| TrueEval 系统失败 | Schema、存储、Grader 崩溃 | 否 |
| SUT 执行失败 | 产品报错、超时、拒答 | 单独统计 |
| 内容质量失败 | 答案错误、引用不支持 | 是，按对应指标 |

## 19. 安全与合规

- API Key 仅从环境变量或 Secret Manager 注入；
- `.trueeval/`、`artifacts/`、Profile 和受保护明文保持 Git 忽略；
- 日志禁止输出 token、Cookie、手机号、二维码、验证码和完整环境变量；
- Artifact 默认私有，报告发布前执行脱敏和许可检查；
- 不自动同意新的产品协议；
- 不绕过登录、验证码、付费墙或 robots 限制；
- 每个正式 Run 记录渠道、账号层级、授权状态和条款核查版本。

## 20. 开发阶段与验收

### Phase 0：Contracts 与骨架

交付：

- Zod Contract；
- JSON Schema 导出；
- 状态机；
- Artifact Store；
- SQLite migration；
- JudgeJob、Judge Profile 和 Fake Judge Contract；
- `validate` CLI。

验收：三套 Benchmark Contract Test 全部通过，执行进程无法读取 gold。

### Phase 1：Batch Runner + 豆包 Facade

交付：

- SUTAdapter Facade；
- 长驻 Browser Worker；
- 一题一会话；
- 五题串行 Batch；
- Checkpoint 和 resume；
- 标准 Artifact 目录。

验收：同一可见 Chrome 连续运行五题；中断恢复不重复提交已确认任务。

### Phase 2：Short Fact 闭环

交付：

- xbench BenchmarkAdapter；
- 官方 Grader Wrapper；
- Grade Command；
- Short Fact Report。

验收：xbench 固定五题可以从执行到评分完整跑通，重复评分结果一致。

### Phase 3：Citation Overlay

交付：

- 豆包 Citation Collector；
- Evidence Resolver；
- Citation/Evidence Schema；
- Citation Entailment Judge、复判和缓存；
- Citation Judge 人工校准集及校准报告；
- 五项引用指标；
- 引用明细报告。

验收：能正确区分产品无引用、Adapter 失败、坏链接、付费墙和可支持证据；Judge 通过预设人工校准阈值后才能进入正式指标。

### Phase 4：Long Form

交付：

- DeepResearchEval Adapter；
- Quality 和 Fact 官方评分包装；
- 长文 Normalizer；
- 长文 Judge 输入切片、全局/局部评分隔离；
- Long Form Report。

验收：至少两道长文题完成执行和双评分，引用 Overlay 可复用。

### Phase 5：第二个 SUT 与 Process Adapter

交付：

- Process Adapter；
- 一个 API 或外部 Agent 脚本；
- 相同任务跨 SUT 运行；
- 渠道隔离报告。

验收：新增 SUT 不修改 Benchmark Adapter 和 Core 状态机。

## 21. AI 开发执行规则

开发 AI 必须遵守：

1. 用户要求一次性交付时，可以在一个连续开发任务中完成全部 Phase，但内部必须按 Phase 0→5 的依赖顺序实施和验证，禁止跳过阶段门；
2. 修改前先读取当前实现和相关 Schema；
3. 不删除已通过真实页面验证的豆包定位逻辑；
4. 优先增加 Facade 和 Contract，再做内部重构；
5. 每个新状态、错误码和 Schema 字段必须有测试；
6. 不用 Mock 结果宣称 Live Test 通过；
7. 不在执行代码中打开 gold；
8. 不用 LLM 代替已有官方确定性评分器；
9. 不静默降级：UI、引用或输出不确定时显式失败或 `not_observable`；
10. 不提交 Artifact、Profile、密钥或受保护 Benchmark 明文；
11. 所有文件路径使用 Run 根目录下的受控相对路径，防止路径穿越；
12. 每个 Phase 完成后运行 typecheck、unit、contract 和对应 integration test；
13. Live Test 必须由用户明确启动，浏览器在整个 Batch 中保持可见；
14. 文档与实现不一致时，先报告差异，再更新版本化 Contract；
15. Judge 必须使用结构化输出、最小输入 allowlist、版本化 Profile 和可审计缓存；
16. 未通过人工校准的 Judge 只能标记为实验性诊断指标；
17. 一次性交付不等于一次提交：允许按可回滚的逻辑单元提交，但最终必须统一通过全量验收。

## 22. MVP 最终验收标准

Research MVP 完成必须同时满足：

1. `validate/run/resume/grade/report/status` 命令可用；
2. xbench 固定五题能由豆包在一个长驻浏览器中连续执行；
3. 每题均创建新对话，无跨题上下文；
4. 已确认提交的任务在进程重启后不会重复提交；
5. 每题包含不可变 Raw Artifact、Research Submission 和 ScoreRecord；
6. Generation 阶段无法读取 gold；
7. 至少一个官方短事实 Grader 能复跑；
8. DeepResearchEval 至少两题完成 quality/fact 双评分；
9. 引用 Overlay 能区分产品行为和采集器失败；
10. 系统失败、产品失败和内容低分分别汇总；
11. 同一冻结产物重复运行确定性 Grader 得到相同结果；
12. 第二个 Agent/API 可以通过 SUTAdapter 或 Process Adapter 接入；
13. 不需要修改 Core 即可新增一个 Benchmark；
14. 报告明确披露 Benchmark 版本、SUT 渠道、账号层级、Adapter 版本和评分器版本；
15. Judge Verdict 能追踪到 Claim、Citation 和 Evidence Span；
16. Judge 的冲突、复判、缓存和人工审查均可审计；
17. Judge 校准结果达到 Rubric 预先声明的阈值。

## 23. 一次性生成与交付顺序

当用户要求开发 AI 一次性生成完整 Research MVP 时，开发 AI 不应在每个 Phase 后等待确认，而应在同一个连续任务中按以下顺序执行：

```text
Phase 0：Contracts、SQLite、Artifact、状态机、Fake Judge
→ 离线最小纵切和默认 CI
→ Phase 1：Batch Runner、豆包 Facade、恢复
→ Phase 2：xbench Short Fact 与官方 Grader
→ Phase 3：Citation、Evidence、Judge、校准
→ Phase 4：DeepResearchEval Long Form
→ Phase 5：Process Adapter 与第二个 SUT
→ 全量 typecheck、unit、contract、integration
→ 用户授权后执行 live smoke test
→ 生成最终实现报告和未完成风险清单
```

一次性生成仍须满足以下约束：

- 每个内部 Phase 验收通过后才能进入下一 Phase；
- 离线测试失败时必须先修复，不能继续堆叠后续模块；
- 真实网页和付费 Judge 调用需要已有账号、登录态、API Key 和用户授权；
- 缺少外部凭据时，完成 Provider 接口、Fake Provider、Contract Test 和清晰的阻塞说明，不能伪造真实测试成功；
- 最终交付是一个完整可运行的工作区，不是大段未落盘的示例代码；
- 所有未实现项必须显式列出，不能用 TODO 假装完成。

第一次内部纵切仍应是：

```text
xbench 一道 TaskSpec
→ Fake SUTAdapter
→ Run/Case/Attempt 状态机
→ RawSUTResult
→ ResearchSubmission
→ Fake Official Grader + Fake Judge
→ report.json
```

该纵切完全离线通过后，开发 AI 应自动继续后续 Phase，而不是停下来请求用户重复确认。
