# ACL26_OPT Walkthrough

## Mission

把 `/data/lv.xiaolei/ACL26_ADI` 包装成一个 AutoOpt 可以持续推进的 **ADI-only** 项目层，并冻结第一版可认真提分的 `acoustic-only` 正式协议。

## Scope

- 只保留阿拉伯语方言识别主线
- 以 `ACL/` 目录为主
- 暂时不接入根目录里那条 `Fusion-GEC` / `ASR correction` 叙事
- `Local` 是最终 gold eval，永不进入训练
- 第一版正式 recipe 在 `ECOschool` 上跑
- `Physical13` 负责 diagnosis、formal dev、Local gold final gate

## What We Already Know

- 根目录 `README.md` 和 `config.json` 指向的是另一条多模态 ASR/GEC 路线
- `ACL/README.md`、`ACL/train.py`、`ACL/model.py`、`ACL/dataset.py` 才是当前 ADI 代码主线
- 当前源训练代码仍然是 PoC 级别，存在明显的“整 shard 直读 / loader 粗糙 / 语义流未真正功能化”等问题
- `ADI17` 没有稳定文本字段，所以第一版正式协议固定为 acoustic-only
- `Local` 与当前公开训练主线未发现直接泄露，但它的部分样本来自 `ADI5` 上游池，因此 `ADI5` 训练接入前必须先做精确排除

## Immediate Goals

1. 冻结 `acoustic_only_baseline_v1`
2. 定义 `acoustic_pilot` non-smoke recipe
3. 在 `ECOschool` 上补齐 conda、tmux、GPU 和 pilot 数据子集
4. 提交 `tmux` 后台训练
5. 在 `formal_dev` 上做独立评测
6. 在 `Local gold` 上做最终 gate
7. 产出 reflection，决定下一步是否该上更高效 loader、全量 shard、或 transcript 增强

## Human Gates

- 如果 `ACL/` 与根目录配置冲突且短时间无法判定真主线，停到 handoff
- 如果正式评测协议被改动，停到 handoff
- 如果 `ECOschool` 缺少 conda、tmux、GPU 或 pilot 数据，停到 handoff
- 如果有人要求把 `Local` 或 `ADI5` 上游池直接并入训练，停到 handoff

## Next After Pilot

- 实现真正的 shard-indexed loader，不再整文件读入后再抽样
- 比较 `formal_dev` 和 `Local gold` 的误差模式，判断下一轮是继续纯声学还是引入受控 transcript
- 只有在 transcript 来源、覆盖率和防泄露策略冻结后，才启用 `dual_stream_controlled_transcript_v1`
- 只有在 `MGB3` / `MGB5` 标签来源被确认后，才把它们从 graylist 升到 whitelist
