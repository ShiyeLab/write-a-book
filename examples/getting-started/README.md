# 从原始资料开始：种子交换登记

本例用原创的种子交换材料和模拟检索记录，演示资料处理到写作、审读的衔接。二进制原件由 [生成脚本](generate_inputs.py) 编写，依赖见 [可选工具](../../docs/optional-tools.md)。

启动请求：请读根 AGENTS 和使用说明，帮我面向首次登记的志愿者整理种子交换资料。先清点文件、提取并检查覆盖、登记来源，再提出目录和样章任务。未知不要补造，本轮不写全文，进度写入本书state。

按顺序打开：

1. [任务与章节职责](brief.md) → [清点](inventory.md)。区分事实、假设与编辑要求。
2. 提取原件；对 [参考转录](reference-transcript.md) 和原始PDF图像核查，不把空响应当空白页。
3. [来源登记](source-register.md) → 运行编号、摘录和索引。工具只核处理底本；归属和含义仍需读。
4. [研究解读](research-note.md) → [材料包](unit-pack.md)。模拟研究的相关结果不能写成因果或推广到发芽率。
5. [初稿](draft.md) → [文风对照](style-review.md) → [修订稿](revised.md)，包含六组修改与两组保留反例。
6. [资料维护](library-update.md)：新增、重复、修订、冲突和归属不清；回查“原件有、索引没有”。
7. [三章统稿](book-review.md) → [出处](references.md) → [已采纳反馈](feedback.md) → [下次任务](next-task.md) → [当前状态](state.md)。

安装格式提取依赖后，从仓库根运行：

```sh
python3 examples/getting-started/replay.py --output /tmp/book-start-example
```

输出必须是新目录。回放实际执行六个文档小样的提取、模拟检索响应归一化、文本编号、摘录核验、索引、旧版拒绝和篇幅计数。混合PDF、复杂Word与模拟失败路线会保留部分完成状态；回放检查这些状态是否符合样本。

本地OCR需另选 macOS Apple Vision 路线，实际命令见 [可选工具](../../docs/optional-tools.md)。参考转录由教学作者提供，用于对照识别结果。brief、审读、改写、反馈和下次任务是预置示范；真实使用时由作者或AI根据自己的材料完成判断。原件来自 [raw](raw/)，生成来源与本例一起交付。
