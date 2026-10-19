# 只删不改与接缝审读

材料性质：原创的1568个基本汉字原文，人物、地点与事件均为教学虚构。

## 使用步骤

1. 通读 [原文](raw/original.md)，再看 [cuts](cuts.json) 的两段删除及理由。
2. 运行示例生成 [纯删节稿](generated/pure.md)、[计数](generated/counts.json)、[标记稿](generated/marked.md) 和 [比较报告](generated/seam-report.json)。
3. 阅读 [接缝审读](review.md)：一处失去铺垫的回指仍存在，工具一致不等于连贯。
4. 用 [任务](task.md) 判断恢复铺垫或另提补写，另存处理意见。

## 运行示例

在仓库根目录运行；输出目录须为新路径：

```sh
run=$(mktemp -d)
python3 examples/replay.py abridgement --output "$run/abridgement"
```

示范稿供阅读比较，回放命令执行本地工具和范围检查。已有检查结果在 [generated](generated/)，逐个工具命令和格式见 [工具说明](../../docs/tools.md)。

自动检查：原文1568、删219、留1349个基本汉字；预算1500。剥离1处接缝、1处补写后与纯删节稿一致。

仍需阅读判断：铅笔回指是否需要恢复铺垫，以及示范补写能否解决接缝。

练习写新稿时，将 task.md 交给所用的 AI 工具，产物保存在自己的书里，再按此例检查。
