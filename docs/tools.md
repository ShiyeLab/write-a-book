# 本地工具

本页介绍八个核心文本工具，均仅依赖 Python 标准库，要求 Python 3.9 或更新版本；本次实际运行版本为 Python 3.9.6。其他版本未逐一验证。本页核心命令离线，不读取账号、不调用模型。下列命令从仓库根运行；脚本本身也可用绝对脚本路径在其他工作目录启动。

通用约定：UTF-8；文本读取将 CRLF／CR 规范为 LF，除此之外不做隐式 Unicode 规范化。命令行路径相对当前工作目录；来源清单内的 path 相对清单所在目录；cuts 的 source 相对显式 `--base`；风格证据 file 相对 `--samples`。工具不自动解析 Markdown 来源卡，使用下述 JSON 契约。

所有输出使用新路径；已存在的文件或目录会报错，不覆盖输入或旧成果。Wiki 先验证输入，再在临时目录构建，完成后移到目标。正确退出为 0，数据、读写或验证失败为 1，命令参数错误为 2。检查报告写到标准输出，需保留时重定向至新文件。扫描命中只是建议，退出仍为 0；规则无效才失败。预算超限默认只报告，强制预算需显式参数。

## 注句级编号

```sh
run=$(mktemp -d)
python3 tools/inject_lines.py examples/source-based/raw/desk.txt --source-id desk --output "$run/desk.txt"
```

输出 `L00001: 内容` 的底本及同名 `.meta.json`，记录相对原件路径、原件与底本 SHA-256、切句算法和段数。L 编号是处理后句段，不能称作原文件物理行号。

沿用中文材料的切句方式：连续物理行直接拼接；空行前未收句时续接；正文按 `。！？!?` 分句，成对引号闭合时收句；超过 200 字的长句先按分号、逗号拆，仍长则每 80 字切。标题单独编号，不依赖标题前后的空行；连续标题各自编号，标题后的正文另行处理。空行不编号。切句算法版本为 `sentence-v2`，包含标题边界修复。OCR 控制字符变为空格，连续空格压为一个，段首尾空白去除。开头连续标题／空行加 `---` 被视作元数据，不编号；原件仍完整保存。英文句中换行可能因直接拼接失去空格，先做好适用文本检查，不用这一步证明原件逐字保真。

## 来源、请求与完整卡片

来源清单为非空 JSON 数组，每份包含 `id`、`path`、`sha256`、`position_type: "sentence-lines"`。示例真实清单见 [sources.json](../examples/source-based/generated/sources.json)。校验值对应带编号底本的原始字节；换底本必须更新版本并重新定位。示例的 replay 会生成清单；自己建清单可读取注编号工具的 `.meta.json` 中 sha256，并填入相对 path。

请求为非空 JSON 数组：

```json
[{"id":"M01","source_id":"desk","location":"L00001-L00002","source_kind":"teaching","attribution":"待确认"}]
```

完整字段要求见 [来源卡模板](../templates/materials/source-card.md)。抽取器保留所有请求元数据，另外写入 `quote`、`source_sha256`、`source_path`。区间为闭区间，只允许 `L数字` 或 `L数字-L数字`；不连续位置请拆成不同卡片，不能悄悄拼起来。正文只去编号前缀及其一个分隔空格，保留内容里的其他空白；区间内各句直接连接，不额外插空格或换行。不再删控制字符或裁剪引文。

```sh
run=$(mktemp -d)
python3 tools/extract_quotes.py examples/source-based/requests.json --sources examples/source-based/generated/sources.json --output "$run/cards.json"
python3 tools/verify_quotes.py "$run/cards.json" --sources examples/source-based/generated/sources.json
```

校验分别报告 location_valid 与 full_text_equal。来源 ID、版本或路径不符，底本缺行、空摘录、尾部缺失、同长度改字及零条输入都会失败。OCR 文字、人物归属和含义需对回原件核查。

## Wiki

输入为完整卡片数组，必须有非空 id、source_id、location、quote。ID 是稳定身份，不从文件顺序自动生成。标签为独立数组，允许 id、topics、keywords、related_ids、summary、title；不允许 quote 或 text 字段覆盖正文。标签可省略，进入“未分类”。分类或关联 ID 不存在、缺正文、重复 ID 均失败。

```sh
run=$(mktemp -d)
python3 tools/build_wiki.py examples/source-based/generated/cards.json --tags examples/source-based/tags.json --output "$run/wiki"
```

输出 entries 正式条目、topics 主题视图、README、关键词索引、ID 路径索引及完整 cards.json。条目中 `<!-- full-quote -->` 后是完整正文，末尾也不强补换行；主题仅链接，不复制计数。ID 与主题名编码为安全文件名，Markdown 链接也编码。条目和主题分别在写入前检查文件名：ID 或不同主题名不能产生仅大小写不同的输出文件名（例如 `M01`／`m01`、`Topic`／`topic`）。发现冲突会报错并返回非零，不留下目标目录；需修改冲突名称后重试。多张卡片引用完全相同的主题可以正常归类。summary 显式标为摘要。工具只负责完整卡片传递与索引，来源保真须先运行 verify_quotes；它不从摘要恢复正文，也不自动生成语义关联。

## 忠实删节

```sh
run=$(mktemp -d)
python3 tools/apply_cuts.py examples/abridgement/cuts.json --base examples/abridgement --output "$run/pure.md" --report "$run/counts.json" --require-budget
```

cuts JSON 必须包含 source（相对 base）、range（原文件物理行号闭区间）、cuts 数组。数组操作二选一：`{"start":3,"end":5,"reason":"删重复"}` 或 `{"line":8,"drop":"唯一子串","reason":"删旁枝"}`。可选正整数 budget；chapter 可作说明。旧格式中的 output 字段不生效，实际路径由 `--output` 决定，避免隐式写回。

依登记顺序删除，整行重复删除不重复计数；已删行不能再行内删。空子串、包括重叠在内的多处命中、未知操作、原范围或删节越界均失败。验证完再写稿。结果保留原句，只压缩连续空行为一空行、整理首尾空白并补一个末尾换行。预算按 U+4E00—U+9FFF 的基本汉字计数，包含范围内标题与注记；不是所有 Unicode 汉字或含标点字符数。

## 接缝与补写

```sh
python3 tools/verify_seams.py examples/abridgement/generated/marked.md examples/abridgement/generated/pure.md
```

只剥离独立成行的 `【接缝：说明】`、`【补写：文字】` 和兼容格式 `【补:文字】`，冒号可中英文，行尾可有空格。不剥离嵌在正文里的标记，也不忽略其他空白。分别输出 seam_lines、addition_lines，再比较剩余全文。带补写的全文含新增内容，不能被说成全部来自原文。

## 文风扫描

```sh
run=$(mktemp -d)
python3 tools/scan_style.py examples/polishing/revised.md --rules tools/style_rules.md --output "$run/style-report.json"
```

规则格式见 [style_rules.md](../tools/style_rules.md)，支持 literal 或 regex。报告给物理行、列、规则 ID、建议与跳过的行；不修改稿件，不输出 AI 率。默认跳过以 `>` 开始的引用行；`--include-quotes` 可显式扫描这些行。始终跳过围栏代码块（反引号或波浪线），其他例外用独立的 `<!-- style:off -->` 与 `<!-- style:on -->` 包围。当前不解析行内代码或复杂 HTML，需将它们放进显式例外范围。未闭合的围栏或例外会失败。没有作者基线，不输出密度判断。

## 风格证据定位

```sh
python3 tools/verify_style_sources.py examples/source-based/style/evidence.json --samples examples/source-based/style/samples
```

证据数组包含 id、file（相对 samples 的文件）、lines（物理行闭区间）、quote。严格模式检查范围内是否出现原样子串，跨行用 LF 连接。`--mode normalized` 将弯引号转直引号并去掉 `…`、`⋯`；`--window 3` 将申报范围前后各扩三行。默认 strict 和 window=0。报告始终记录模式和窗口；完整区间摘录的全文核验使用 verify_quotes。零条、规范化后空引文、缺文件、越界、改字或范围内未命中均失败。

## 检查与运行示例

```sh
python3 -m unittest discover -s tests -v
run=$(mktemp -d)
python3 examples/replay.py source-based --output "$run/source-based"
python3 examples/replay.py true-stories --output "$run/true-stories"
python3 examples/replay.py abridgement --output "$run/abridgement"
python3 examples/replay.py polishing --output "$run/polishing"
```

运行示例实际执行本地工具和范围比较，不调用 AI，不重新生成预置正文。阅读判断和生成新稿的任务见各示例 README 与 task.md。

## 按需使用的工具

PDF、Office 提取，Apple Vision／云 OCR、可配置多路检索和网页采集见 [可选工具](optional-tools.md)。这些工具有独立依赖、配置和部分完成状态，不属于上述标准库承诺。原始资料到写作的衔接见 [新教学示例](../examples/getting-started/README.md)。
