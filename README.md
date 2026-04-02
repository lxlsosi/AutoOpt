# AutoOpt

`AutoOpt` 是一个“外部状态机 + 短 agent turn + 外部数据/算力适配器 + 强评测约束”的自动算法工程师骨架。它默认先用规则型 worker 跑通链路，后续你可以把同样的 contract、state、tool registry 接到真实的 Codex / OpenAI Responses worker 上。

## 核心思路

- 任务本体在你自己的状态库里，不在 LLM thread 里。
- 每个 turn 只做一小步，并且每步后 checkpoint。
- 算法训练和数据处理是外部 job，agent 负责发起、轮询、分析、决策。
- `walkthrough.md` 是项目 contract 的自然语言补充，不是随手记 TODO。
- 达到人工 Gate 时，系统自动停到 `handoff`。

## 目录

```text
autoopt/                  Python 框架
docs/                     架构说明
templates/                通用项目模板
Arab/                     阿语方言分类专项示例
walkthrough.md            根目录 walkthrough 模板
```

## 关键对象

- `contract.json`: 项目目标、预算、约束、评测、数据策略、人工闸门
- `project.json`: tool registry、phase 规则、运行时配置
- `execution_topology`: 控制机、执行机、路由 profile、主机角色
- `JobState`: 任务状态，持久化在 `<project>/.autoopt/jobs/<job_id>.json`
- `artifacts/`: 数据、分析、训练、评测产物

## 状态流

```text
queued -> diagnose -> propose -> execute -> evaluate -> reflect -> handoff/done/failed
```

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

autoopt run --project Arab/project.json --job-id arab-demo --max-turns 12
autoopt inspect --project Arab/project.json --job-id arab-demo
autoopt remote bootstrap --project Arab/project.json --host ECO01
```

上面的 `Arab/` 是一个可本地跑通的 mock 项目。它会生成以下几类 artifact：

- `artifacts/data/*.json`
- `artifacts/analysis/*.json`
- `artifacts/metrics/*.json`
- `.autoopt/jobs/*.json`

## 后续如何接真实 Codex / OpenAI

默认 worker 是 `rule-based`，用于把 orchestration 骨架跑通。之后你可以切到：

```bash
OPENAI_API_KEY=... autoopt run \
  --project Arab/project.json \
  --job-id arab-openai \
  --worker openai \
  --model gpt-5.4
```

当前仓库里的 `OpenAIResponsesWorker` 是一个最小骨架：

- 输入是外部持久化的 state + contract + walkthrough + tool registry
- 输出是结构化 JSON 决策
- 默认 `store=false`
- 预留了 `context_management` compaction 参数

## 控制机与 GPU 执行机

推荐把 `AutoOpt` 按“两层”部署：

- 控制层：在装好 Codex / OpenAI 凭证的机器上跑 `autoopt run`
- 执行层：把真正的数据处理、训练、验证任务路由到指定机器

框架现在支持在 `project.json` 里声明 `execution_topology`，并把每次工具调用的目标机写入 state。

对于 compute 工具，执行器会在本地运行你的包装脚本，同时注入这些占位符：

- `{execution_host}`
- `{execution_mode}`
- `{execution_project_root}`
- `{ssh_target}`

以及对应环境变量：

- `AUTOOPT_EXECUTION_HOST`
- `AUTOOPT_EXECUTION_MODE`
- `AUTOOPT_EXECUTION_PROJECT_ROOT`
- `AUTOOPT_SSH_TARGET`

这样你可以在 `Physical13` 上跑 orchestrator，再由脚本决定是本地小规模验证，还是通过 `ssh` / 队列系统把训练提交到 `ECO01`、`ECO04`、`ECOschool`。

建议第一次先在 `Physical13` 上执行：

```bash
autoopt remote bootstrap --project Arab/project.json --host ECO01
autoopt remote bootstrap --project Arab/project.json --host ECO04
autoopt remote bootstrap --project Arab/project.json --host ECOschool
```

这会做三件事：

- 导出当前激活的 conda 环境
- 同步代码和项目数据到远端 workspace
- 在远端创建或更新同名 conda env

## 你接真实项目时的建议

1. 先复制 `templates/` 的模板，补出自己的 `contract.json`、`project.json`、`walkthrough.md`。
2. 把 `tool_registry` 里的 shell 命令换成你们实际的数据平台、GPU 平台、评测脚本。
3. 把 mock `train.py` 替换成真实提交训练任务的命令，例如 Slurm、K8s、Ray、Airflow 或内部平台 CLI。
4. 冻结 gold eval，严禁 agent 改测试集。
5. 给高风险动作加 `requires_approval=true` 或 contract 里的人工 Gate。

更多细节见 [docs/ARCHITECTURE.md](/Users/momo/Git/AutoOpt/docs/ARCHITECTURE.md)。
