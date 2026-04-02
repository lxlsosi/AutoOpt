# Arab Dialect Classification Demo

这是一个专项模板，演示如何把通用 `AutoOpt` 框架落到“阿拉伯语方言分类”场景。

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

## 你后面要替换的点

- `scripts/data_pipeline.py`
- `scripts/train.py`
- `scripts/evaluate.py`
- `project.json` 中的 tool commands

建议把真实平台动作做成 shell/CLI 边界，这样 orchestrator 不需要知道平台细节。
