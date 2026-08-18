# Agent Benchmark：25 个目标产品 Web 自动化可行性核查

> 日期：2026-08-17  
> 当前阶段：Research 类 5 个目标产品  
> 项目代号：TrueEval  
> 文档状态：方向决策稿 + 第一轮可行性核查  
> 暂定目标：OpenAI Deep Research、Gemini Deep Research、Perplexity Research、Genspark Deep Research、Manus Research / Wide Research

## 一、0817 结论

1. **Research 五个目标均存在可程序化调用路径，技术上可进入自动 Benchmark。** OpenAI、Gemini、Perplexity、Manus 有官方 API；Genspark 有官方 CLI 的 `deep_research` 任务及 JSON 输出。
2. **TrueEval 第一阶段应做“评测工作流框架”，而不是完整自主 Agent。** MVP 的核心是统一任务、统一调用、统一留痕、统一评分；Agent 式交互可以作为外层入口，不能成为底层不可复现的执行逻辑。
3. **必须接入现有数据集，但不能只接一个公开数据集。** 建议采用“公开静态集 + Live 动态集 + 私有保留集”的三层结构。
4. **API 自动化与 Web 产品评测必须分轨。** 同一品牌的 API 模型未必等价于消费者网页中的最新产品。排行榜必须明确标注 `surface=api | web | cli`，不能把 API 得分冒充 Web 产品得分。
5. **当前还不是 5/5 端到端验证完成。** 本轮已确认官方调用面和数据/评分方案；当前环境没有五家的 API 凭据，也不允许直接自动操作这些对话站点，因此尚未真实提交付费任务。状态应写为“接口可行，待凭据烟测”，而不是“已跑通”。

## 二、Research 五个目标的自动化可行性

### 2.1 判定口径

自动 Benchmark 不等于“能在网页里填一个输入框”。一个目标进入 TrueEval，至少要满足：

- 可将同一条 Benchmark prompt 无损提交；
- 可异步等待长任务完成，且有明确的完成、失败、需人工输入状态；
- 可自动取得完整报告、引用链接和附件；
- 可记录产品/模型版本、参数、耗时、成本、重试和人工干预；
- 批量运行时不依赖每题人工点击；
- 调用方式不违反产品条款，不依赖验证码绕过或非官方逆向接口；
- 能说明被测对象到底是 Web 产品、API 模型还是 CLI 工作流。

### 2.2 核查结果

| 目标产品 | 首选适配面 | 官方能力证据 | 技术自动化 | 与 Web 产品等价性风险 | 当前结论 |
|---|---|---|---:|---:|---|
| OpenAI Deep Research | API / Responses | 官方提供 Deep Research 专用模型，可搜索互联网和 MCP 数据；支持流式输出。参考 [o3-deep-research 模型文档](https://developers.openai.com/api/docs/models/o3-deep-research) 与 [ChatGPT Deep Research 产品说明](https://openai.com/index/introducing-deep-research/)。 | A | 中—高 | **可接入，待真实凭据烟测。** API 模型与 ChatGPT 当期网页体验需视为两个 target variant。 |
| Gemini Deep Research | Gemini Interactions API | 官方 Deep Research Agent 支持后台执行、轮询、最长 60 分钟；典型任务官方估算约 1–3 美元。参考 [Gemini Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research?hl=en)。 | A- | 中 | **可接入，待烟测。** 当前为 preview，必须锁定 agent ID，并记录版本变化。 |
| Perplexity Research | Sonar API async | `sonar-deep-research` 可异步提交、轮询结果，并返回 citations、搜索次数、reasoning token 和成本。参考 [Sonar Deep Research](https://docs.perplexity.ai/docs/sonar/models/sonar-deep-research)。 | A | 高 | **可接入，但必须拆成 API Track。** 2026 年网页端 Advanced Deep Research 使用的订阅模型策略与 Sonar API 不完全等价，不能混榜。参考 [Advanced Deep Research 更新](https://www.perplexity.ai/help-center/en/articles/13600190-what-s-new-in-advanced-deep-research)。 |
| Genspark Deep Research | 官方 CLI | `@genspark/cli` 支持 `gsk task deep_research`、API Key、超时设置和 JSON 输出。参考 [Genspark CLI](https://www.npmjs.com/package/@genspark/cli)。 | B+ | 中 | **可接入，先做 CLI 烟测。** 需要核验 CLI Deep Research 与网页 Deep Research 的模型、工具和报告格式是否一致。 |
| Manus Research / Wide Research | Manus API v2 | 官方 API 可创建任务、多轮追问、取回结果、注册 webhook；支持 JSON Schema 后处理。参考 [Manus API v2](https://open.manus.im/docs/v2/introduction)、[Structured Output](https://open.manus.im/docs/v2/structured-output)。Wide Research 为自动触发且面向付费用户。参考 [Wide Research](https://help.manus.im/en/articles/11960169-what-is-wide-research)。 | A- | 中—高 | **通用 Research 可接入；Wide Research 需单独验收。** “自动触发”会导致同一题是否进入 Wide 模式不可完全控制，必须记录实际执行模式。 |

### 2.3 优先级

建议接入顺序：

1. **Perplexity Sonar API**：异步接口、引用、使用量和成本字段最完整，最适合验证 Runner 数据结构。
2. **Gemini Deep Research API**：原生后台任务，可验证 10–60 分钟长任务的状态机。
3. **Manus API v2**：webhook、文件、结构化结果齐全，可验证多轮 `needs_input` 流程。
4. **OpenAI Deep Research API**：能力明确，但先确认 2026-08-17 实际可用模型/快照，避免接入已迁移的旧 alias。
5. **Genspark CLI**：先确认官方 CLI 的稳定性、认证方式、任务返回结构与产品等价性，再决定是否补 Web 适配器。

### 2.4 两条排行榜，禁止混榜

| Track | 被测对象 | 运行方式 | 优点 | 局限 |
|---|---|---|---|---|
| Programmatic Track | 官方 API / 官方 CLI 能力 | 自动批量运行 | 可复现、可扩展、成本和错误可观测 | 可能不等价于消费者 Web 产品 |
| Product Web Track | 用户在网页实际购买和使用的功能 | 受控浏览器适配器 | 最贴近真实产品体验 | UI 易变、登录/验证码/订阅限制多、复现成本高 |

TrueEval MVP 先完成 Programmatic Track。Web Track 只用于确实没有程序化入口，或需要验证“网页产品真实体验”的目标；不得使用 Cookie 逆向、私有接口或验证码绕过。

## 三、市面上成熟 Benchmark：Research 模块选型

### 3.1 第一梯队：MVP 应接入

| Benchmark | 主要测什么 | 规模/形式 | 评分特点 | MVP 用法 |
|---|---|---|---|---|
| DeepResearch Bench | 长篇研究报告的完整性、深度、指令遵循、可读性、引用可信度 | 100 个专家任务，22 个领域，中英文各 50 | RACE 评报告质量；FACT 评引用准确率和有效引用数 | **主评测集。** 先抽 10 题做 pilot，后续再全量。官方仓库：[DeepResearch Bench](https://github.com/Ayanami0730/deep_research_bench)。 |
| LiveDRBench | 高 fan-out 搜索、关键 claim 发现、证据覆盖 | 100 个动态 Research 任务，8 类 | 基于结构化 ground truth，计算 Precision / Recall / F1；弱化长文写作风格 | **客观补充集。** 先抽 5–10 题，重点验证事实发现。官方仓库：[Microsoft LiveDRBench](https://github.com/microsoft/livedrbench)。 |
| BrowseComp | 持久、创造性的深网事实检索 | 1,266 个难找但答案简短的问题 | 短答案易自动评分；不测长报告质量 | **检索能力子分。** 先抽 10 题。官方介绍：[BrowseComp](https://openai.com/index/browsecomp/)。 |
| AssistantBench | 现实、耗时、多网站的信息任务 | 214 题，覆盖 258 个网站和 525+ 页面 | Accuracy、Answer Rate、Precision、Exact Match；测试集答案隐藏 | **真实任务补充。** 先使用 dev 集，不把隐藏 test 当本地回归集。官方站点：[AssistantBench](https://assistantbench.github.io/)。 |

### 3.2 第二梯队：后续扩展

- **GAIA**：适合测通用助手的推理、浏览、多模态与工具使用；不能替代长篇 Research 质量评价。参考 [GAIA 论文](https://ai.meta.com/research/publications/gaia-a-benchmark-for-general-ai-assistants/)。
- **FRAMES**：824 个多跳问题，适合拆出 factuality、retrieval、reasoning 子分，不直接评价完整研究报告。参考 [FRAMES 数据集](https://huggingface.co/datasets/google/frames-benchmark)。
- **SimpleQA**：适合做短事实准确率和拒答校准，不足以代表 Deep Research。参考 [SimpleQA](https://openai.com/index/introducing-simpleqa/)。
- **ResearcherBench**：面向前沿、尚未解决的 AI 研究问题，适合高端研究洞察评估，但人工/LLM rubric 成本更高。参考 [ResearcherBench](https://openreview.net/forum?id=oj6A9hrNdL)。
- **DeepResearch Bench II、DRBench、DeepScholar-Bench**：可在 MVP 稳定后补充专家报告 rubric、企业 Research 和学术综述场景。

### 3.3 不建议的做法

- 只跑一个公开 Benchmark，然后对外声称“Research Agent 综合第一”；
- 只用一个 LLM Judge 打总分；
- 将长文长度、引用数量直接当作研究质量；
- 把 API 版和网页订阅版放在同一行排名；
- 公开展示 BrowseComp 等测试集的题目—答案对，造成数据泄漏；
- 不记录日期、产品版本、订阅档位、地区和成本，导致分数不可复现。

## 四、TrueEval 产品形式决策

### 4.1 决策：先做工作流框架，外层再包装 Agent

TrueEval 的第一性价值不是“替用户聊天”，而是**可复现地执行和解释评测**。因此建议：

```text
数据集注册表
   ↓
任务编译器（统一 prompt / 附件 / 输出要求）
   ↓
目标适配器（OpenAI / Gemini / Perplexity / Genspark / Manus）
   ↓
异步 Runner（队列、限流、重试、超时、needs_input）
   ↓
原始证据仓（完整响应、引用、附件、日志、成本）
   ↓
标准化器（report / citations / structured claims）
   ↓
评测器（确定性规则 + Benchmark 官方评测 + LLM Judge + 人审）
   ↓
可比报告 / 排行榜
```

完整 Agent 可以作为第二阶段的自然语言控制层，例如“帮我评测这 5 个产品在金融 Research 上的表现”；底层仍应生成一份不可变的 Eval Plan，经用户确认后交给同一个工作流执行。

### 4.2 Research MVP 必须有的模块

| 模块 | MVP 范围 |
|---|---|
| Dataset Registry | 接入 3–4 个数据源；保存版本、许可、语言、答案是否密封、评分方法 |
| Target Registry | 产品、surface、订阅档位、地区、模型/agent ID、调用限制、价格版本 |
| Adapter SDK | `submit()`、`poll()`、`resume()`、`cancel()`、`collect()` 五个统一接口 |
| Runner | 并发、速率限制、指数退避、幂等、超时、人工输入暂停、断点续跑 |
| Artifact Store | 原始输入/输出、引用 URL、附件、时间戳、哈希、错误和成本 |
| Normalizer | 统一抽取正文、引用、claim、表格和文件，不修改原始产物 |
| Evaluator | Exact Match / F1、引用支持度、任务 rubric、至少一个可替换 LLM Judge |
| Report | 总分、分项、成本、延迟、成功率、人工干预率及逐题证据 |

### 4.3 不进入 MVP 的内容

- 25 个领域一次性全部接完；
- 面向普通用户的复杂聊天 Agent；
- 自动购买订阅、自动登录、验证码处理；
- 公开大榜单和商业化计费；
- 训练或微调新的 Research Agent；
- 用浏览器逆向私有接口。

## 五、LLM 测评数据集：是否接入现有数据集

### 5.1 决策：接入，但采用“三层数据资产”

| 层 | 占比建议 | 作用 | 是否公开 |
|---|---:|---|---|
| Public Regression | 40% | 对齐已有论文和排行榜，验证实现正确性 | 题目通常公开；答案按原 Benchmark 规则处理 |
| Live / Rotating | 30% | 降低污染，测试新鲜信息和真实网页变化 | 定期更新，延迟公开 |
| Private Holdout | 30% | 防刷榜，覆盖 TrueEval 用户真实场景 | 不公开答案，必要时题目也不公开 |

建议先“接入测试集”，而不是“导入训练集”。Benchmark 数据与答案必须与生产提示词、日志检索、Agent memory 隔离，防止无意泄漏。

### 5.2 数据接入门槛

每个数据集进入 Registry 前必须填写：

- 数据集版本、commit hash、下载日期；
- 许可证及商业使用限制；
- train/dev/test 划分和答案可见性；
- 是否有 canary、禁止公开样例或 leaderboard 提交规则；
- 题目是否依赖动态网页、地区、语言、订阅数据库；
- Ground truth 的生成与复核方式；
- 官方 evaluator 版本及 Judge 模型版本；
- 已知污染风险与过期策略。

许可方面需单独审查：例如 LiveDRBench 的代码为 MIT、数据集为 CDLA v2，仓库同时明确其主要面向研究与复现，不建议未经进一步测试直接用于商业或高风险实际决策。参考其 [官方 README](https://github.com/microsoft/livedrbench)。

### 5.3 评分策略

总分不应由单一 LLM Judge 决定。建议 Research MVP 的分数结构为：

| 分项 | 权重建议 | 评价方式 |
|---|---:|---|
| 任务完成与指令遵循 | 15% | 结构规则 + rubric judge |
| 事实/claim 正确性 | 25% | Ground truth、Precision / Recall / F1、抽样人审 |
| 引用支持度 | 20% | claim—URL 对齐、来源可访问性、引用是否真正支持 claim |
| 覆盖与研究深度 | 20% | task-specific rubric，参考报告但不做文本相似度 |
| 分析与洞察 | 10% | 双 Judge + 人工校准 |
| 可读性与交付质量 | 5% | rubric |
| 效率 | 5% | 成功率、延迟、成本、人工干预率 |

Judge 风险控制：

- Judge 模型和 prompt 均版本化；
- 每次升级 Judge 都重跑固定 calibration set；
- 至少 10% 样本双人或专家抽审；
- 高主观维度采用两个不同模型 Judge，分歧过大进入人审；
- 报告同时展示原始子分，避免总分掩盖事实错误；
- Judge 不知道被测产品名称，减少品牌偏差和同源模型偏好。

## 六、Research MVP 的最小实验设计

### 6.1 Phase 0：接入烟测

目标：证明 5 个 Adapter 能可靠提交、等待和取回结果，而不是比较模型强弱。

- 每个目标 2 题：1 个长报告题 + 1 个短事实检索题；
- 共 10 次正式运行；
- 禁止并发，先确认状态机、输出和成本字段；
- 每个目标至少验证 1 次失败/超时或 `needs_input` 的恢复流程；
- 保存原始报告、引用、附件、任务 ID、耗时、成本和产品版本。

通过门槛：10/10 能形成完整、可重放的 Run Record；若失败，错误必须被正确归类且可安全重试。

### 6.2 Phase 1：小规模 Benchmark Pilot

建议题目：

- DeepResearch Bench：10 题（5 中文、5 英文，跨领域）；
- BrowseComp：10 题；
- LiveDRBench：5 题；
- 私有新鲜任务：5 题。

共 30 题 × 5 个目标 = 150 个 runs。为测稳定性，其中 5 题对每个目标重复 3 次；重复运行单独计费并用来估计方差。

Pilot 验收门槛：

- 提交成功率 ≥ 98%；
- 最终产物自动获取率 ≥ 95%；
- 引用解析成功率 ≥ 95%；
- 每题人工操作中位数 = 0；
- 失败任务平均重试次数 ≤ 1；
- 相同题重复运行的核心分数方差可解释；
- 每一分都能回到原始产物和评分证据；
- 100% 区分 API / CLI / Web，不发生混榜。

### 6.3 统一 Run Record

```json
{
  "run_id": "uuid",
  "task_id": "dataset:version:item_id",
  "target": "perplexity",
  "surface": "api",
  "product_variant": "sonar-deep-research",
  "region": "CN|US|...",
  "subscription_tier": "api-tier-x",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "status": "completed|failed|timeout|needs_input|cancelled",
  "attempt": 1,
  "human_interventions": 0,
  "input_hash": "sha256",
  "raw_artifact_uri": "immutable://...",
  "normalized_report_uri": "...",
  "citations": [],
  "usage": {},
  "cost_usd": null,
  "scores": {},
  "adapter_version": "git-sha",
  "evaluator_version": "git-sha"
}
```

## 七、接下来两周的执行顺序

### 第 1–2 天：锁定对象与规则

- 确认 Research 五个产品是否就是本文暂定名单；
- 确认首期只做 Programmatic Track，还是必须同时交付 Web Track；
- 建立 Target Registry 与 Dataset Registry；
- 完成数据许可与产品条款审查清单。

### 第 3–6 天：做三个核心 Adapter

- Perplexity、Gemini、Manus；
- 统一异步状态机、原始产物格式和错误分类；
- 用自造的非 Benchmark prompt 完成低成本烟测。

### 第 7–9 天：补 OpenAI 与 Genspark

- 确认 OpenAI 当期有效 Deep Research 模型/快照；
- 安装并验证 Genspark 官方 CLI，核对网页产品等价性；
- 完成 5 × 2 题 Phase 0。

### 第 10–12 天：接入评测器

- 先接 BrowseComp / LiveDRBench 的确定性评分；
- 再接 DeepResearch Bench 的 RACE / FACT；
- 建立 Judge calibration set 和 10% 人审流程。

### 第 13–14 天：生成第一份 TrueEval 报告

- 展示质量、引用、稳定性、耗时、成本、失败率；
- 对 API / CLI / Web 明确分轨；
- 根据 Phase 0 决定是否值得启动 150-run Pilot。

## 八、当前阻塞项

1. **目标名单待确认**：本文按五个主流 Research 产品暂定；若原始 25 产品清单不同，应以原表为准。
2. **凭据与预算缺失**：当前环境未检测到 OpenAI、Gemini、Perplexity、Manus、Genspark 的 API 凭据，也未安装 `gsk` CLI，因此无法完成真实付费任务烟测。
3. **Web Track 无法在本轮实测**：当前浏览器安全策略禁止自动操作这五个对话站点；不能使用其他浏览器、私有接口或验证码绕过规避。此项只能在允许的专用测试环境中，以测试账号完成。
4. **等价性待验证**：尤其是 Perplexity 网页 Advanced Deep Research 与 Sonar API、Genspark CLI 与网页 Deep Research、Manus 普通 Research 与自动触发 Wide Research。

## 九、最终建议

**立即立项 Research Workflow MVP，先不做完整 Agent。**

首期目标不是做一个“会评测的聊天机器人”，而是做出一条可靠流水线：同一批题可以送到五个产品，长任务能够异步完成，原始证据不会丢，评分可以解释，成本与失败可以比较，任何人都能在相同版本下复跑。

数据上，接入现有 Benchmark 是必要条件，但 TrueEval 的长期壁垒不会是“搬运公开题库”，而应是：

- 产品级适配器和长期稳定运行能力；
- API / Web 产品等价性审计；
- 私有、动态、真实任务集；
- 可解释、可校准、多证据的评分体系；
- 对版本、成本、延迟、稳定性和人工干预的完整追踪。
