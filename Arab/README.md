# Arab Dialect Classification Demo

这是一个专项模板，演示如何把通用 `AutoOpt` 框架落到“阿拉伯语方言分类”场景。

这个版本默认使用本地可运行拓扑：

- `local-controller`: 控制机，负责跑 Codex / orchestrator、数据步骤、mock 训练和评测
- `gpu-worker-01` / `gpu-worker-02` / `gpu-worker-03`: 可选远端占位示例，不会被默认 quickstart 调用

默认 quickstart 不需要 SSH、GPU、私有共享盘或远端 conda 环境。远端 worker 配置只用于展示 `execution_topology` 的扩展方式。

框架会把每一步执行目标写进 job state 的 `execution_history`。当前 demo 里训练脚本是 mock，目的是让 orchestrator、state、artifact contract 和人工 gate 可以在本地稳定验证。

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

如果你要试验远端 dispatch，可以先把 `project.json` 中的 `gpu_train` routing profile 改到某个 `remote_gpu_train` host，然后在 `local-controller` 上执行：

```bash
autoopt remote bootstrap --project Arab/project.json --host gpu-worker-02
autoopt remote bootstrap --project Arab/project.json --host gpu-worker-03
autoopt remote bootstrap --project Arab/project.json --host gpu-worker-01
```

远端训练链路支持后台 job 模式：

- 第一次 `run` 会提交远端训练
- 训练进程会挂在远端 `tmux` session 中
- job 运行中时，state 里会出现 `pending_jobs`
- 后续 `run` 会自动轮询远端状态
- 完成后会把 logs、checkpoint、metrics 拉回本地

## 你后面要替换的点

- `scripts/data_pipeline.py`
- `scripts/train.py`
- `scripts/evaluate.py`
- `project.json` 中的 tool commands

建议把真实平台动作做成 shell/CLI 边界，这样 orchestrator 不需要知道平台细节。
