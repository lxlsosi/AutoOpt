# AutoOpt Architecture

## 1. 设计原则

- 任务是状态机，不是一次超长对话。
- 记忆以外部状态和 artifact 为准，不以 thread 上下文为准。
- 长时间动作交给外部 job 系统，agent 只负责编排。
- 每次 turn 都要留下 checkpoint、摘要、失败路径和产物引用。
- 先冻结 contract，再让 agent 优化，不让 agent 重写目标。

## 2. 项目文件

每个项目最少要有三个文件：

1. `walkthrough.md`
2. `contract.json`
3. `project.json`

如果项目要跨机器执行，建议把 `execution_topology` 也当成稳定配置的一部分，直接放进 `project.json`。

### `contract.json`

定义稳定约束：

- objective
- success_metrics
- frozen_eval_sets
- constraints
- data_policy
- compute_policy
- human_gates

### `project.json`

定义执行层：

- `tool_registry`
- `decision_rules`
- `runtime`
- `execution_topology`

工具注册表示例：

```json
{
  "discover_data": {
    "adapter": "data",
    "description": "Catalog candidate datasets",
    "command": "python3 scripts/data_pipeline.py discover --project-root {project_root} --result-json {result_json}",
    "produces_artifacts": ["artifacts/data/source_catalog.json"],
    "budget_cost": 5
  }
}
```

决策规则示例：

```json
{
  "name": "discover sources",
  "when": {
    "missing_artifacts": ["artifacts/data/source_catalog.json"]
  },
  "phase": "diagnose",
  "tools": ["discover_data"],
  "summary": "Catalog candidate sources before any training.",
  "followup_phase": "propose"
}
```

## 3. 状态字段

框架默认持久化这些字段：

- `job_id`
- `thread_id`
- `phase`
- `attempts`
- `attempts_by_tool`
- `goal`
- `completed_steps`
- `failed_approaches`
- `artifacts`
- `last_summary`
- `deadline_at`
- `dataset_version`
- `eval_suite_version`
- `latest_metrics`
- `best_metric`
- `metrics_history`
- `gpu_job_id`
- `budget_spent`
- `approval_required`
- `hypotheses_tried`
- `blocked_reason`
- `last_execution_target`
- `pending_jobs`
- `execution_history`
- `phase_history`
- `checkpoints`

## 4. 执行拓扑

推荐把机器分成两类：

- 控制机：跑 orchestrator、worker、state store、summary
- 执行机：跑数据下载、训练、验证，或者承接提交后的异步 job

典型拓扑：

```json
{
  "execution_topology": {
    "controller_host": "Physical13",
    "default_local_host": "Physical13",
    "default_compute_hosts": ["ECO01", "ECO04", "ECOschool"],
    "routing_profiles": {
      "data_ops": ["Physical13"],
      "evaluation": ["Physical13"],
      "gpu_train": ["ECO01", "ECO04", "ECOschool"]
    }
  }
}
```

关键点不是让 orchestrator 直接长驻 GPU 机器，而是让 orchestrator 只负责决策，把目标机和选路理由写进状态，再由包装脚本或平台 adapter 提交实际任务。

对于长训练，推荐模式是：

1. 当前 turn 只提交后台 job
2. 在 state 里记录 `pending_jobs`
3. 下一个 turn 只做 poll
4. 任务完成后回收 logs / checkpoint / metrics，再进入 evaluate

## 5. 推荐接入方式

### 数据侧

- 搜索/枚举数据源
- 下载和校验
- 生成清洗 manifest
- 记录 license、checksum、覆盖范围、泄漏风险

### 算力侧

- 提交训练任务
- 获取 job id
- 轮询状态
- 收集 metrics / checkpoints / model path

### 评测侧

- 固定 benchmark
- confusion matrix
- per-class recall
- 不合格原因定位

## 6. 为什么先做 rule-based

`rule-based worker` 的价值不是替代 LLM，而是先把下面这些稳定件搭好：

- 状态机边界
- checkpoint 粒度
- artifact 协议
- 工具调用协议
- 人工接管条件

这些稳定后，再把 worker 换成 Codex / OpenAI Responses，系统才不会“一换脑子就散架”。

## 7. 真接生产时该替换什么

- 把 `ShellAdapter` 替换成内部平台 adapter
- 把 mock `scripts/*.py` 替换成真实提交/轮询脚本
- 把 `OpenAIResponsesWorker` 的 prompt 变成你们自己的 agent contract
- 把 `.autoopt/jobs` 换成 DB / Redis / Postgres / Temporal state

如果你们是 `Physical13 -> ECO01/ECO04/ECOschool` 这种架构，比较自然的替换方式是：

- 保留 orchestrator 在 `Physical13`
- `train.py` 之类脚本读取 `AUTOOPT_EXECUTION_HOST`
- 由脚本决定 `ssh`、`sbatch`、`ray job submit` 或内部调度接口
- 结果摘要和 job handle 回写本地 `result_json`

如果真实工程已经存在，推荐把 AutoOpt 当成控制平面单独放一层：

- `Arab/` 这种目录是 AutoOpt 项目层
- 真正的训练工程通过软链接接入，例如 `source_project -> /real/path/project`
- 让 Codex 在 AutoOpt 项目层改 wrappers / adapters / decision rules
- 尽量少直接改真实训练工程，除非已经明确好变更范围

## 8. 人工 Gate 建议

- 外部数据源 license 不确定
- 要花大额 GPU 预算
- 指标异常波动
- 怀疑数据泄漏
- 连续同类失败
- 想改测试集、标签口径或上线阈值
