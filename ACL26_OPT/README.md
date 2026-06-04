# ACL26_OPT

`ACL26_OPT` 是 `ACL26_ADI` 的 AutoOpt 项目层，目标是把原始研究工程包装成一个可编排、可诊断、可逐步自动优化的 **ADI-only** 项目。

## 范围

- 只做 `ADI`（Arabic Dialect Identification）
- 不接入根目录 `README.md` 里那条 `ASR/GEC` 叙事
- 优先包装 `ACL/` 子目录中的 `Hi-CoDi` 训练线
- 所有适配配置都放在当前目录

## 当前正式协议

- 官方 baseline: `acoustic_only_baseline_v1`
- 第一版可认真提分的正式 recipe: `acoustic_v1`
- 快速试跑 recipe: `acoustic_pilot`
- 训练主机: `gpu-worker-01`
- 冻结 dev: `formal_dev`
- 最终 gate: `Local gold`

`Local` 只用于最终评测，永不进入训练。`ADI5` 上游原池在做完严格去重前也不进入训练。

## 路径约定

- 原始项目: `/data/autoopt-workspace/ACL26_ADI`
- 控制面: `/data/autoopt-workspace/AutoOpt/ACL26_OPT`
- GPU 工作区: `/data/autoopt-workspace/AutoOpt`
- GPU 源数据根: `/data/autoopt-workspace/ACL26_ADI`

## 推荐流程

1. 在 `local-controller` 上同步当前仓库到 `/data/autoopt-workspace/AutoOpt`
2. 在 `local-controller` 上先准备 `rclone`
   `bash ACL26_OPT/scripts/bootstrap_rclone.sh`
3. 用 `rclone -> object storage -> /data` 方案做大数据 staging
   `bash ACL26_OPT/scripts/launch_acl26_stage_tmux.sh upload ALL`
   然后在 GPU worker 上运行 `bash /data/autoopt-workspace/AutoOpt/ACL26_OPT/scripts/launch_acl26_stage_tmux.sh materialize ALL`
4. 运行 `conda run -n AutoOpt python -m autoopt remote bootstrap --project ACL26_OPT/project.json --host gpu-worker-01`
5. 运行 `conda run -n AutoOpt python -m autoopt run --project ACL26_OPT/project.json --job-id acl26-acoustic-v1 --max-turns 12`
6. 如果出现 `pending_jobs`，再次运行同一个 `job-id` 继续 poll，直到进入 `done`

## 环境

- 远端 conda 模板: [config/remote_environment.yml](config/remote_environment.yml)
- 远端 pip 依赖: [requirements.autoopt.txt](requirements.autoopt.txt)
- 远端补环境脚本: [bootstrap_autoopt_env.sh](scripts/bootstrap_autoopt_env.sh)

## 关键脚本

- 正式训练: [train_acl26.py](scripts/train_acl26.py)
- 评测入口: [evaluate_acl26.py](scripts/evaluate_acl26.py)
- GPU worker 就绪检查: [verify_eco_ready.py](scripts/verify_eco_ready.py)
- rclone 安装: [bootstrap_rclone.sh](scripts/bootstrap_rclone.sh)
- object storage staging: [stage_acl26_via_rclone.sh](scripts/stage_acl26_via_rclone.sh)
- 后台 staging: [launch_acl26_stage_tmux.sh](scripts/launch_acl26_stage_tmux.sh)
