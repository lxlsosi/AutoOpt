# Arabic Dialect Classification Walkthrough

## Mission

搭建一个能够自动推进阿语方言分类项目的算法工程师。它需要先判断主要瓶颈是在数据、标签、分布偏移还是模型方案，再调用对应动作，而不是一上来就暴力训更多模型。

## Target

- 主指标：`macro_f1 >= 0.82`
- 守门指标：`rare_dialect_recall >= 0.70`
- 冻结评测：`arab_dev_gold_v1` / `arab_test_gold_v1`

## Non-Negotiables

- 不允许改动冻结评测集
- 不允许使用 license 不明确的数据
- 不允许跳过 checksum / dedup / leakage review
- 昂贵训练 recipe 最多再试一次，然后交由人判断

## Data Playbook

优先看这些问题：

1. 各方言样本是否严重不平衡
2. 是否有明显 domain shift，例如新闻播报对社交口语
3. 是否存在重复说话人或重复文本导致泄漏
4. 是否存在标注口径不一致

若数据不足，优先动作：

- 搜索并枚举更多公开或已授权数据源
- 做 license / checksum / split 风险审计
- 生成统一 manifest
- 记录每个方言的覆盖与风险

## Model Playbook

基础路线：

- encoder + classifier baseline
- class-balanced sampling
- 针对低资源方言做更强增广
- 保留 confusion matrix 和按方言召回

## Reflect Questions

每次失败后必须回答：

- 低分主要集中在哪些方言
- 是数据覆盖问题还是建模问题
- 下一个动作为什么比“再训一遍 baseline”更有信息增益

## Handoff Rules

以下情况必须 handoff：

- license 风险不清楚
- 预算接近上限
- 指标波动反常
- 两轮高成本方案后仍不达标
