# 可选文风提示规则

这是编辑定位词表，命中不等于写错，也不判定文本来源。可复制到单书目录调整。扫描器只读取下方唯一 JSON 代码块；每条有稳定 id、literal 或 regex、pattern、suggestion。不使用密度阈值。引文默认跳过，代码块始终跳过；例外见工具说明。

```json
[
  {
    "id": "abstract-action",
    "kind": "literal",
    "pattern": "赋能",
    "suggestion": "核对是否能写清谁做了什么；术语必要时保留。"
  },
  {
    "id": "contrast",
    "kind": "regex",
    "pattern": "不是.{0,30}而是",
    "suggestion": "判断对照是否帮助理解；不要机械删除。"
  },
  {
    "id": "dash",
    "kind": "literal",
    "pattern": "——",
    "suggestion": "核对停顿是否必要；作者习惯、对话与忠实引用可以保留。"
  },
  {
    "id": "summary",
    "kind": "literal",
    "pattern": "总而言之",
    "suggestion": "检查后文是否只是重复，或是否确需总结。"
  },
  {
    "id": "preview",
    "kind": "literal",
    "pattern": "接下来我们将",
    "suggestion": "检查是否仅预告结构；确有导航需要可保留。"
  },
  {
    "id": "empty-praise",
    "kind": "literal",
    "pattern": "令人惊叹",
    "suggestion": "核对是否有具体对象和依据，避免空泛赞叹。"
  },
  {
    "id": "personified-argument",
    "kind": "literal",
    "pattern": "数据不会说谎",
    "suggestion": "核对数据来源、口径与限制，不让拟人判断代替论证。"
  },
  {
    "id": "process-leak",
    "kind": "literal",
    "pattern": "通篇检索零命中",
    "suggestion": "区分内部检查记录与正文；技术说明可保留，零命中不能证明原件没有。"
  }
]
```
