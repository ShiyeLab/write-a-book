# 按需要安装的工具

八个[核心文本工具](tools.md)仍只需 Python 标准库。本页工具处理非文本原件或外部搜索，按实际需要安装；阅读方法、手工研究和 TXT 写作不受这些条件限制。以下命令从项目根目录运行，输出用新的独立目录，原件不改写。示例输出路径再次运行前应换一个名字。

接口资料核对日期：2026-10-19。使用者按当前官方文档和账号权限填写模型，通过指定的环境变量提供凭证。

## 文档提取

入口：[extract.py](../tools/extraction/extract.py)。输入一个或多个文件，输出编号 Markdown 和 `report.json`，含原件版本、逐对象位置、状态及覆盖限制。文本随后经原件抽查，进入 [来源登记](../templates/materials/source-register.md)和核心工具的编号、摘录步骤。

| 输入 | 依赖 | 实际覆盖与限制 |
|---|---|---|
| DOCX | Python 标准库 | 按正文顺序读取段落和顶层表格；检测数学公式、文本框、嵌套表格、图像、脚注等未覆盖对象；不复刻版面 |
| PDF | PyMuPDF | 每一物理页的文字层、页标及状态，按内容流顺序（不按坐标重排，避免双栏交错）；扫描页交 OCR；无文字页仍待核，图像区域不因已有文字而自动算完成 |
| PPTX | python-pptx | 每页文字框和表格；图片、组合对象、备注、图表等另列覆盖限制，不推断阅读顺序 |
| XLSX | openpyxl | 工作表名、单元格位置、公式与缓存分开；日期类缓存保留类型；不计算公式，不提取图表文字 |
| XLS | xlrd | 工作表、行列位置及保存的值；公式表达式和图像等不在覆盖范围 |

需要 Python 3.9+。可只安装某种格式的依赖，例如 `python3 -m pip install PyMuPDF`。需要全部格式时，建议先建自己的虚拟环境，再安装 [依赖清单](../tools/extraction/requirements.txt)：

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r tools/extraction/requirements.txt
python3 tools/extraction/extract.py examples/getting-started/raw/registration.docx examples/getting-started/raw/mixed.pdf --output /tmp/book-extract-demo
```

混合 PDF 的预期退出值为 3，表示文字页已处理，扫描页和空白候选页待处理。`success`／`partial`／`failed` 对应 0／3／1，参数错误为 2；未处理项为 `not_processed`。缺库会在报告内给出库名和安装提示，不能把无输出当成功。每完成一个输入就保存进度，整批中断后可在新目录仅处理剩余输入；不对旧目录隐式覆盖。

有 Word 修订时默认拒绝提取。明确选择 `--revision-view original`（修订前）或 `--revision-view accepted`（采用修订后的读取视图），只是选择读取口径，不修改原件或替作者接受修订。例如：

```sh
python3 tools/extraction/extract.py examples/getting-started/raw/complex.docx --revision-view original --output /tmp/book-complex-demo
```

此小样仍应报告部分完成：文本框和嵌套表格未覆盖。Word 数学公式列入 `unsupported.office_math`，`unsupported_ranges` 标出所在段落或表格的正文顶层位置（`document.xml/body/序号`）。普通文字照常保留，含未处理公式的文件返回部分完成／3；只有公式而无可用正文时返回失败／1。

XLSX 的日期、时间、日期时间缓存以 ISO 8601 字符串保存，`cached_type` 分别为 `date`、`time`、`datetime`；时长类型为 `timedelta`，`cached_value` 保存 `days`、`seconds`、`microseconds`（分别以天、秒、微秒计），三项相加还原时长。数字、布尔、文本和空缓存保留原类型，公式表达式另列。

报告写入失败会记录到对应输入，继续处理后续文件；报告通过临时文件替换，保留上一次完整进度。若输出目录持续无法写入，命令以失败退出并报告 `report_write_failed`。

## 逐页 OCR

入口：[ocr.py](../tools/extraction/ocr.py)。输入 PDF，逐页生成文本、页记录、合并文本、绑定文件和报告。`--pages 1,2,4` 指物理页序，不是印刷页码；不选则处理全部页。仅选部分页时，全文件报告仍保留未处理页。`--dpi` 可设 72—600，默认 200。

### 本地 Apple Vision

仅 macOS；需要 PyMuPDF、ocrmac 和适配 Python 的 PyObjC。以下依赖清单兼容 Python 3.9：

```sh
python3 -m pip install -r tools/extraction/requirements-apple.txt
python3 tools/extraction/ocr.py examples/getting-started/raw/mixed.pdf --engine apple --output /tmp/book-apple-demo
```

默认语言 `zh-Hans,en-US`，可用 `--languages` 调整。教学 PDF 的第三页没有文字，报告 `empty_needs_review`，需查看原页确认。在禁止系统 OCR 服务的沙盒中可能失败，需要支持该系统能力的运行环境；失败仍保留逐页记录。

### 可选云端 OCR

Gemini 和 Cloud Vision 都需要 PyMuPDF 生成页图；HTTP 部分只用标准库。Gemini 另需显式 `--model`。Key 由使用者在环境中设置，`--key-env` 只填一个变量名，缺失报 ABSENT，不回退到其他 Key。下面只展示命令形状，须在自己已配置并授权调用后运行：

```sh
python3 tools/extraction/ocr.py input.pdf --engine gemini --model YOUR_SELECTED_MODEL --key-env BOOK_OCR_GEMINI_KEY --execute --output /tmp/book-gemini-ocr
python3 tools/extraction/ocr.py input.pdf --engine cloud-vision --key-env BOOK_OCR_VISION_KEY --execute --output /tmp/book-cloud-ocr
```

不加 `--execute` 不会调用云端。`--responses teaching-pages.json` 可离线回放“页序字符串 → 服务响应对象”，不得与真实调用混用。Gemini 须有完成标记和有效文本，Cloud Vision 须有匹配的页面响应且无错误；空值、错误 JSON、受理标识和截断会记为失败。

网络超时 `--timeout` 单位秒，可设 1—180；`--retries` 为 0—2，默认不重试，仅明确的 429 限流可自动重试。未知结果先查服务端状态，不自动重复提交。`--resume` 仅复用同原件、页范围、引擎、模型、语言、DPI 和模式下内容完整且校验一致的成功页；修改原件或参数会拒绝。未知页默认仍跳过，只有确认可安全重试后才显式加 `--retry-unknown`。新的有效页保留，失败页不进入合并正文。

成功表示提取到了文本，质量仍为 `not_reviewed`。按 [提取方法](../methods/text-extraction.md)核页覆盖、数字、人名、表格和实际引用；不能用模型一致性替代原件抽查。报告 0／3／1 分别为成功／部分完成／无成功页。

### 对照辅助

[compare.py](../tools/extraction/compare.py)只需标准库，比较可疑模式密度与关键词，不输出“真实准确率”：

```sh
python3 tools/extraction/compare.py /tmp/book-apple-demo/text.md --pattern '一—' --keyword '批次编号' --output /tmp/book-ocr-compare.json
```

单位是每万字符命中数，公式为命中次数／字符数 × 10000；空文本分母不计算。命中只是待审信号，人工参考转录与原件才支持错漏判断。

## 可配置多路搜索

入口：[search.py](../tools/research/search.py)，使用 Python 标准库。先读 [研究方法](../methods/research.md)，确定问题，再选能实际使用的渠道。一路可用一路；十路或更多可添加到配置，路线 ID 自定且唯一，不以服务品牌限制数量。

开始调研时可以提示：“如需扩大覆盖，可增加搜索 API、数据库或其他来源；也可先用现有渠道继续。”不强制补齐配置。中文资料可以先尝试 DeepSeek 的可用搜索能力，再按需补豆包、千问、Kimi、百度等；这不是效果排名或固定调用顺序。配置样例的排列仅便于查找，执行由 `--routes` 显式选择。

[无密钥配置样例](../tools/research/providers.example.json)中，每条路线包含 ID、接口协议、endpoint、单一 `key_env`，需要模型的接口还需 `model`。环境变量名也可自行改；不读取其他候选变量。复制到自己的图书目录后，只填写当前账号可用的模型，示例不固定版本。

| 已提供的协议适配 | 可选使用方向 |
|---|---|
| `deepseek_search` | DeepSeek 独立 Search API，不需要模型字段 |
| `responses_annotations` | 豆包等返回引用注释的 Responses 搜索接口 |
| `responses_action_sources` | 千问等返回 action.sources 的 Responses 搜索接口 |
| `qianfan_ai_search` | 百度 AI Search |
| `gemini_grounding` | Gemini 搜索依据 |
| 实际搜索记录导入 | Kimi、宿主 AI 或其他搜索工具 |

提供者名单可以增减；相同协议可配置多条路线。接口协议不同的新服务，需按官方文档补适配，或导入实际搜索记录。Kimi 官方帮助当前提示旧搜索能力正在更新，可先使用实际搜索记录导入。导入记录中的 provider 可自行命名，须保留问题、实际搜索确认、回答、直接来源及是否模拟；样例见 [native-record.example.json](../tools/research/native-record.example.json)。`--native-record` 可重复给多个文件。

帮助和预检均不请求服务：

```sh
python3 tools/research/search.py --help
python3 tools/research/search.py --preflight --routes deepseek
```

预检报告变量名、PRESENT/ABSENT 和是否已填模型。真实检索在自己配置与授权后显式开启，例如：

```sh
python3 tools/research/search.py --config books/my-book/providers.json --routes deepseek --query '你的研究问题' --execute --output /tmp/book-research
```

多路例子是 `--routes route-a,route-b,route-c --concurrency 2`；数字仅示例，用户可自行选择正整数。默认逐路，实际并发不超过所选路线数，不规定必须达到某个并发数。并发不改变报告中所选路线的顺序；不要为凑数量发送重复问题。服务的查询长度、速率和结果条数按当前官方接口约束处理，配置的 `top_k` 是每次结果数，不是并发数。

离线教学可直接运行：

```sh
python3 tools/research/search.py --routes doubao,qwen,qianfan,gemini --query '教学：如何安排登记' --responses examples/getting-started/search-responses.json --native-record examples/getting-started/native-search.json --output /tmp/book-search-demo
```

这个教学记录有失败路线，预期 `partial`／退出 3；全部可用为 0，无可用结果为 1，命令参数错误为 2。模拟供应商组合只服务测试，不是用户必选组合。无来源、空文本、未完成响应、错误 JSON 或缺 Key 不能当成功。重复 URL 与已声明的原始来源会分组，不同网址可能仍同源，必须人工检查。所有输出保持 `evidence_eligible: false`，打开原件并核对后才进入写作证据。

单路脱敏归一化结果放在 `routes/<路线ID>.json`，根目录保留 `binding.json` 和 `report.json`，不保存供应商原始响应。旧布局无法直接续跑，会提示使用新输出目录并保留旧结果。每完成一路即落盘；`--resume` 只复用同问题、所选配置与模式下完整且校验一致的结果。超时、有限重试及未知结果处理与云 OCR 相同；未知状态查明后用 `--retry-unknown` 重试。调整并发或超时不会改变材料版本绑定。

## 网页采集与独立视觉转录

入口：[capture.mjs](../tools/web-capture/capture.mjs)、[vlm-bridge.mjs](../tools/web-capture/vlm-bridge.mjs)。需要 Node.js 22.12+、npm、Playwright 浏览器及 [package.json](../tools/web-capture/package.json)中的依赖。使用 [锁文件](../tools/web-capture/package-lock.json)安装；也可用 `--browser` 指定自己已有的兼容浏览器：

```sh
npm --prefix tools/web-capture ci
npm --prefix tools/web-capture exec -- playwright install chromium
node tools/web-capture/capture.mjs 'https://example.org/page' --output /tmp/book-web-page
```

输出父目录须存在，目标目录须为新目录。默认用 DOM／Readability 提取正文，只保存可读 `body.md` 和 `metadata.json`，不自动保存截图、上传图像或调用视觉服务。`--timeout` 单位毫秒，可设 1000—180000；`--min-text` 调整候选正文最少字符，默认 80。

获取状态 `acquired` 和内容状态 `content` 分开。登录、验证码、付费墙、拒绝访问等字样记入 `accessSignals`，只作核对提示：这些字样常出现在导航或按钮中（如“登录后复制”），不阻止提取正文。取得足够正文时仍保存为候选，但状态降为部分完成，须回原页确认是否只是试读片段；未取得正文时，信号用于说明原因。空页不生成正文。`needs_source_review` 表示候选正文，仍须回原页核对。返回 0 表示采集到候选正文且无访问信号，3 表示正文保留但有访问信号或另选的视觉步骤未完成，1 表示未取得正文。短通知、复杂页面可能被保守过滤，需人工审阅；不自动登录或绕过访问限制。

`--screenshot` 显式保存 `page.png`。如已授权上传截图，可用单独转录命令：

```sh
node tools/web-capture/vlm-bridge.mjs --image /tmp/book-web-page/page.png --output /tmp/book-web-vision --config books/my-book/vision-providers.json --routes YOUR_ROUTE --execute
```

从 [视觉配置样例](../tools/web-capture/providers.example.json)复制并填自己的模型和变量名；所选一路可独立运行，未选服务缺 Key 不阻止它。支持 Gemini 和 chat-completions 视觉响应，单路文本及记录保存到 `routes/<路线ID>.md`、`routes/<路线ID>.json`，根目录保留绑定和总报告。旧布局会提示使用新输出目录。`--responses` 可离线回放；`--resume` 绑定截图、所选配置和模式，成功文本校验后复用，未知结果须查明后显式 `--retry-unknown`。超时有上限，无自动重试。也可在采集时显式加 `--execute-vision --vision-config FILE --vision-routes a,b`，两步结果仍分别报告。

工具遵从用户代理环境，不在导入时改写 `NO_PROXY`；不导入浏览器个人账号。带鉴权查询参数的输入 URL 不发送；鉴权参数按精确名称识别（如 `api_key`、`access_token`、`token`、`signature`、`*_token`、`X-Amz-*`），`keyword`、`author` 等普通参数保留，检索来源 URL 同样按此规则清理；错误日志不打印请求头或原始响应。

## 环境与教学回放

Python 和 Node 版本要求见各组工具；依赖版本在 requirements 文件和 npm 锁文件中给出。Apple Vision 需要 macOS，网页采集需要能够启动浏览器的环境。配置外部服务后先用自己的一个小样检查响应与来源，再扩大处理范围。

原创二进制小样由 [生成脚本](../examples/getting-started/generate_inputs.py)提供；重建另需 python-docx 1.2.0、Pillow 11.3.0、xlwt 1.3.0，它们不属于提取必需依赖。重建新目录：

```sh
python3 -m pip install python-docx==1.2.0 Pillow==11.3.0 xlwt==1.3.0
python3 examples/getting-started/generate_inputs.py --output /tmp/book-original-inputs
python3 examples/getting-started/replay.py --output /tmp/book-start-example
python3 -m unittest discover -s tests/optional -v
```

视觉续跑测试运行 `node --test tests/optional/vision-resume.test.mjs`，使用离线响应。网页行为测试另运行 `node tests/optional/web-capture.test.mjs`，需要可启动浏览器和监听本地端口的环境；已安装系统浏览器时可用测试变量 `BOOK_TEST_BROWSER` 指定路径。测试只访问受控本地页面，视觉响应使用模拟数据。

接口和依赖核对依据：[PyMuPDF](https://pymupdf.readthedocs.io/en/latest/page.html)、[python-pptx](https://python-pptx.readthedocs.io/en/latest/api/shapes.html)、[openpyxl](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html)、[xlrd](https://xlrd.readthedocs.io/en/latest/)、[ocrmac](https://github.com/straussmaximilian/ocrmac)、[Playwright](https://playwright.dev/docs/library)、[代理处理](https://github.com/nodejs/undici/blob/main/docs/docs/api/EnvHttpProxyAgent.md)。云接口：[Gemini](https://ai.google.dev/api/generate-content)、[Cloud Vision](https://cloud.google.com/vision/docs/reference/rest/v1/images/annotate)、[DeepSeek 搜索](https://api-docs.deepseek.com/zh-cn/guides/search/)、[豆包](https://docs.volcengine.com/docs/ark/web-search?lang=en)、[千问](https://help.aliyun.com/en/model-studio/web-search)、[百度](https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u)、[Gemini 搜索](https://ai.google.dev/gemini-api/docs/google-search)、[Kimi 当前说明](https://www.kimi.ai/help/kimi-api/api-troubleshooting)。
