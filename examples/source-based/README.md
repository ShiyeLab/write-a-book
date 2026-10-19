# 来源到一个说明单元

材料性质：三份虚构观察／草案／讨论记录；十二张素材卡；两份同题稿。

## 使用步骤

1. 读 [来源清单](source-list.md) 与 raw 中三份原件，确认材料性质。
2. 运行下方命令，生成句级底本、十二张卡、正文校验、主题 Wiki、风格证据报告和长摘录测试。
3. 从 [Wiki](generated/wiki/README.md) 取材，读 [素材包](unit-pack.md) 和 [关系索引](relations.md)。
4. 比较 [A稿](candidate-a.md) 与 [B稿](candidate-b.md)，查看 [选择说明](comparison.md)、[改后稿](revised.md) 与 [审读](review.md)。
5. 按 [完整任务](task.md) 生成自己的候选，另存正文与审读记录；风格证据方法见 [style](style/README.md)。

## 运行示例

在仓库根目录运行；输出目录须为新路径：

```sh
run=$(mktemp -d)
python3 examples/replay.py source-based --output "$run/source-based"
```

示范稿供阅读比较，回放命令执行本地工具和范围检查。已有检查结果在 [generated](generated/)，逐个工具命令和格式见 [工具说明](../../docs/tools.md)。

自动检查：十二条全文比较、三条风格定位通过。长测试摘录分别 700、6130 字符，均无末尾换行，Wiki 完整保留。long-fixtures.json 仅为机械测试，不充当正文资料。

仍需阅读判断：来源是否支持论点、U1 与 U2 的职责、缺口是否合理。U2 留作后续写作任务。

练习写新稿时，将 task.md 交给所用的 AI 工具，产物保存在自己的书里，再按此例检查。
