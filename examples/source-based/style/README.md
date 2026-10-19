# 风格证据演示

三篇 samples 中的文字是新写教学样本。evidence.json 保留原样引文和物理行范围；rules.md 展示规则、反例与边界。

在仓库根目录运行：

```sh
python3 tools/verify_style_sources.py examples/source-based/style/evidence.json --samples examples/source-based/style/samples
```

结果应为 strict、window=0、3 条匹配。normalized 仅演示规范化口径：给同一命令加 `--mode normalized`。需要定位偏移时显式指定 `--window`；完整连续摘录的保真检查仍使用 verify_quotes。
