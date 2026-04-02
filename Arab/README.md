# Arab Dialect Classification Demo

这是一个专项模板，演示如何把通用 `AutoOpt` 框架落到“阿拉伯语方言分类”场景。

这个版本已经内置一套机器拓扑：

- `Physical13`: 控制机，负责跑 Codex / orchestrator，也能跑小规模 GPU 验证
- `ECO01`
- `ECO04`
- `ECOschool`

目前配置按你最新补充的信息处理成：

- 三台 GPU 机都看作 `8 x A100`
- 三台机器共享 `/data` 盘
- 远端 workspace 默认放在 `/data/AutoOpt`
- 远端项目目录默认放在 `/data/AutoOpt/Arab`

这意味着代码和数据同步是“共享盘优先”的，一份同步可被三台机器复用；conda 环境仍然会在每台机器上各自创建和校准。

框架会把每一步执行目标写进 job state 的 `execution_history`。当前 demo 里训练脚本还是 mock，但接口已经换成真实可路由的形态了。

## 这个示例做了什么

- 发现候选数据源
- 审核数据可用性和泄漏风险
- 生成清洗后的 dataset manifest
- 跑 baseline
- 评测 baseline
- 如果不达标，先 reflect，再跑改进版 recipe
- 再评测，如果达标则 `done`，否则 `handoff`

## 这个示例没有做什么

- 没有真的下载公网数据
- 没有真的提交 GPU 集群任务
- 没有真的训练神经网络

这些部分现在是 mock 脚本，目的是先把 orchestrator、state、artifact contract、人工 Gate 这些稳定下来。你后面把脚本替换成真实训练/下载命令就行。

## 运行

```bash
autoopt run --project Arab/project.json --job-id arab-demo --max-turns 12
autoopt inspect --project Arab/project.json --job-id arab-demo
```

如果你要先把三台 GPU 机预热好，建议先在 `Physical13` 上执行：

```bash
autoopt remote bootstrap --project Arab/project.json --host ECO01
autoopt remote bootstrap --project Arab/project.json --host ECO04
autoopt remote bootstrap --project Arab/project.json --host ECOschool
```

这会把当前激活的 conda 环境导出成锁定文件，然后同步代码/数据到 `/data/AutoOpt`，并在目标机器上创建或更新 `AutoOPT` conda 环境。

## 你后面要替换的点

- `scripts/data_pipeline.py`
- `scripts/train.py`
- `scripts/evaluate.py`
- `project.json` 中的 tool commands

建议把真实平台动作做成 shell/CLI 边界，这样 orchestrator 不需要知道平台细节。
