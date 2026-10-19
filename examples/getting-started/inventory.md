# 清点与处理安排

| 输入 | 来源 ID／性质 | 路线 | 接续 |
|---|---|---|---|
| raw/registration.docx | D1 教学说明 | DOCX顺序提取；对回表格 | 阅读范围、章节1材料 |
| raw/complex.docx | D2 复杂对象教学 | 先选修订视图；报告文本框与嵌套表格缺失 | 不把纯正文当完整原稿 |
| raw/mixed.pdf | P1 混合教学PDF | 第1页文字层、第2页扫描、第3页空白待核 | OCR／参考转录对照，记录覆盖与质量 |
| raw/brief.pptx、counts.xlsx、legacy.xls | T1—T3格式小样 | 按对象／单元格提取 | 表格值和公式缓存分开 |
| raw/supplement-v1.txt | S1-v1 原始教学记录 | 直接读、编号 | 首次建卡 |
| raw/supplement-v2.txt | S1-v2 修订版 | 重新编号 | 核受影响卡片及下一任务 |
| raw/new-note.txt | S2 新资料 | 直接读、登记 | 第二章材料 |

这些原件不改写。生成过程见 generate_inputs.py。实际提取记录由 replay.py 生成，不能用本表代替运行结果。
