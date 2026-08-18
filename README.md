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
