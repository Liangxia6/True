# TrueEval

TrueEval 是面向多领域 Agent / API 的统一评测框架。本仓库当前先实现 Research MVP，以及豆包网页版的浏览器自动化适配器。

## 仓库结构

```text
benchmarks/  Research 测试集、上游锁定文件、官方评分适配器
docs/        架构、产品适配器和使用文档
scripts/     Benchmark 入库与本地解密脚本
src/         TrueEval 执行代码和豆包网页适配器
tests/       TypeScript 单元测试
artifacts/   本地运行产物，不进入 Git
```

当前已接入 BrowseComp-ZH、xbench-DeepSearch 和 DeepResearchEval，数据状态与使用限制见 [Benchmark 目录说明](benchmarks/README.md)。

## 豆包自动化 MVP

已支持：

- 使用独立、可复用的 Chrome Profile 保存登录态；
- 自动创建新对话并选择“深入研究”；
- 自动输入并提交提示词；
- 等待回复稳定后提取正文和页面可见来源信息（交互式来源 URL 提取仍待补充）；
- 保存统一 JSON 结果、可见文本、原始 HTML、事件日志和截图；
- UI 变化、未登录、提交未确认、服务异常和超时均显式失败，不输出伪结果。

```bash
npm install
npm run doubao -- --prompt "请调研一个具体问题"
```

首次运行会打开 Chrome；在该窗口登录豆包一次后，登录态会保存在 `.trueeval/profiles/doubao`，后续任务可复用。

详细参数与产物格式见[豆包网页版自动化脚本使用说明](docs/adapters/doubao/使用说明.md)，设计约束见[开发规格](docs/adapters/doubao/开发规格_V0.1.md)，全部文档入口见[文档索引](docs/README.md)。

## 统一 Research 评测工作流

Phase 0–5 的代码链路已经实现：Benchmark、网页/API/Process SUT、状态恢复、LLM Judge、引用 Overlay、DeepResearchEval 官方薄包装和报告。完全离线模式使用 Fake SUT/Judge 验证协议，不代表真实产品成绩。

```bash
npm install
npm run schemas:export
npm run trueeval -- validate --manifest manifests/offline-fixture-smoke.yaml
npm run trueeval -- run --manifest manifests/offline-fixture-smoke.yaml
```

`run` 返回 `runId` 后可以继续：

```bash
npm run trueeval -- grade --run-id <runId>
npm run trueeval -- report --run-id <runId>
npm run trueeval -- status --run-id <runId>
```

上面的离线命令不调用真实网页或付费 LLM Judge。真实 Judge 配置示例见 `configs/judges/openai-compatible.example.yaml`，API Key 只通过其中声明的环境变量传入，不写进配置或 Artifact。

外部 Agent 可按 JSONL 进程协议接入并完成同一测试集的端到端测试：

```bash
npm run trueeval -- validate --manifest manifests/process-fixture-smoke.yaml
npm run trueeval -- run --manifest manifests/process-fixture-smoke.yaml
```

HTTP Research API 使用 `http_api` Adapter；请求只包含公开 Task Input，响应统一为 `answer`、`citations` 和可选 usage 字段。完整实现边界与尚需凭据的 Live 验收见[实现状态](docs/development/IMPLEMENTATION_STATUS.md)。

豆包五题 Batch 配置已经提供，但下面的 `run` 会真实打开浏览器并向豆包提交题目，只应由用户明确启动：

```bash
npm run trueeval -- validate --manifest manifests/doubao-xbench-2505-smoke.yaml
npm run trueeval -- run --manifest manifests/doubao-xbench-2505-smoke.yaml
```

Batch 中复用一个 Chrome 和登录态，每道题新建对话。中断后使用 `resume --run-id <runId>`；处于提交不确定或运行中的 Case 不会自动重发，而会等待人工确认。
