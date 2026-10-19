"""把文本整理为句级编号副本；原件保持不变。"""
import re
import argparse
import os
from pathlib import Path
from _common import read, write_new, check_output, digest, encode, run

CTRL_CHARS = str.maketrans({'\x0b': ' ', '\x0c': ' ', '\x1c': ' ', '\x1d': ' ', '\x1e': ' ', '\x1f': ' ', '\u2028': ' ', '\u2029': ' ', '\x85': ' '})
SENT_END = '。！？!?'
LDQUO = '“'
RDQUO = '”'
LSQUO = '‘'
RSQUO = '’'
QUOTE_PAIRS = {LDQUO: RDQUO, LSQUO: RSQUO, '「': '」', '『': '』', '《': '》'}
QUOTE_OPEN = set(QUOTE_PAIRS.keys())
QUOTE_CLOSE = set(QUOTE_PAIRS.values())
TRAIL_QUOTE = set(QUOTE_CLOSE) | {'"', "'"}
HEADING_RE = re.compile('^#{1,6}\\s+\\S')
LONG_SENT_THRESHOLD = 200
HARD_CUT_LEN = 80

def is_heading_line(line: str) -> bool:
    """是否是 markdown 标题行（# / ## / ###...）。"""
    return bool(HEADING_RE.match(line.strip()))

def split_sentences(text: str) -> list:
    """把一个段落（已去掉换行符的纯文本）按句切分。

    返回完整句子列表，每句保留原标点。空字符串/全空白跳过。

    引号语义：
    - 成对中文引号 / 书名号（""''「」『』《》）通过引号栈追踪。
    - ASCII 直引号 "/' 用奇偶计数器追踪（来源 OCR 几乎不会出现）。
    - 在引号内遇到句末符号 → 不切，但设 pending_close 标志：
      当对应的右引号闭合后立即切。
    - 句末符号紧跟一组右引号 / 直引号 → 把它们一并收进本句句末。
    """
    text = text.strip()
    if not text:
        return []
    sentences = []
    buf = []
    quote_stack = []
    quote_open_pos = []
    straight_double = 0
    straight_double_pos = -1
    straight_single = 0
    straight_single_pos = -1
    pending_close = False
    MAX_QUOTE_SPAN = 120

    def in_quote_now(cur_pos):
        nonlocal straight_double, straight_single
        while quote_stack and cur_pos - quote_open_pos[-1] > MAX_QUOTE_SPAN:
            quote_stack.pop()
            quote_open_pos.pop()
        if straight_double == 1 and cur_pos - straight_double_pos > MAX_QUOTE_SPAN:
            straight_double = 0
        if straight_single == 1 and cur_pos - straight_single_pos > MAX_QUOTE_SPAN:
            straight_single = 0
        return bool(quote_stack) or straight_double == 1 or straight_single == 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        buf.append(ch)
        was_in_quote = in_quote_now(i)
        if ch in ('「', '『', '《'):
            quote_stack.append(QUOTE_PAIRS[ch])
            quote_open_pos.append(i)
        elif ch == LDQUO:
            quote_stack.append(RDQUO)
            quote_open_pos.append(i)
        elif ch == LSQUO:
            quote_stack.append(RSQUO)
            quote_open_pos.append(i)
        elif ch in ('」', '』', '》'):
            if quote_stack and quote_stack[-1] == ch:
                quote_stack.pop()
                quote_open_pos.pop()
        elif ch == RDQUO:
            if quote_stack and quote_stack[-1] == RDQUO:
                quote_stack.pop()
                quote_open_pos.pop()
        elif ch == RSQUO:
            if quote_stack and quote_stack[-1] == RSQUO:
                quote_stack.pop()
                quote_open_pos.pop()
        elif ch == '"':
            if straight_double == 0:
                straight_double = 1
                straight_double_pos = i
            else:
                straight_double = 0
        elif ch == "'":
            if straight_single == 0:
                straight_single = 1
                straight_single_pos = i
            else:
                straight_single = 0
        now_in_quote = in_quote_now(i)
        if ch in SENT_END and was_in_quote:
            pending_close = True
            i += 1
            continue
        if pending_close and was_in_quote and (not now_in_quote):
            j = i + 1
            while j < n and text[j] in TRAIL_QUOTE:
                buf.append(text[j])
                cc = text[j]
                if cc in ('」', '』', '》'):
                    if quote_stack and quote_stack[-1] == cc:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == RDQUO:
                    if quote_stack and quote_stack[-1] == RDQUO:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == RSQUO:
                    if quote_stack and quote_stack[-1] == RSQUO:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == '"':
                    straight_double = 0 if straight_double == 1 else 1
                elif cc == "'":
                    straight_single = 0 if straight_single == 1 else 1
                j += 1
            sentences.append(''.join(buf).strip())
            buf = []
            pending_close = False
            i = j
            continue
        if ch in SENT_END and (not now_in_quote):
            j = i + 1
            while j < n and text[j] in TRAIL_QUOTE:
                buf.append(text[j])
                cc = text[j]
                if cc in ('」', '』', '》'):
                    if quote_stack and quote_stack[-1] == cc:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == RDQUO:
                    if quote_stack and quote_stack[-1] == RDQUO:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == RSQUO:
                    if quote_stack and quote_stack[-1] == RSQUO:
                        quote_stack.pop()
                        quote_open_pos.pop()
                elif cc == '"':
                    straight_double = 0 if straight_double == 1 else 1
                elif cc == "'":
                    straight_single = 0 if straight_single == 1 else 1
                j += 1
            sentences.append(''.join(buf).strip())
            buf = []
            i = j
            continue
        i += 1
    tail = ''.join(buf).strip()
    if tail:
        sentences.append(tail)
    out = []
    for s in sentences:
        out.extend(_split_long(s))
    return out

def _split_long(s: str) -> list:
    """对超长句子做二级切：先 `；`，再 `，`，再 ~80 字硬切。"""
    if len(s) <= LONG_SENT_THRESHOLD:
        return [s]
    parts = _split_keep_delim(s, '；;')
    if all((len(p) <= LONG_SENT_THRESHOLD for p in parts)) and len(parts) > 1:
        return parts
    further = []
    for p in parts:
        if len(p) <= LONG_SENT_THRESHOLD:
            further.append(p)
        else:
            sub = _split_keep_delim(p, '，,')
            if all((len(x) <= LONG_SENT_THRESHOLD for x in sub)) and len(sub) > 1:
                further.extend(sub)
            else:
                further.extend(_hard_cut(p, HARD_CUT_LEN))
    return further

def _split_keep_delim(s: str, delims: str) -> list:
    """按 delims 中任一字符切，分隔符保留到前一段末尾。"""
    out = []
    buf = []
    for ch in s:
        buf.append(ch)
        if ch in delims:
            out.append(''.join(buf).strip())
            buf = []
    tail = ''.join(buf).strip()
    if tail:
        out.append(tail)
    return [x for x in out if x]

def _hard_cut(s: str, n: int) -> list:
    """每 n 字硬切一段。"""
    return [s[i:i + n] for i in range(0, len(s), n)] if s else []

YAML_LINE_RE = re.compile('^(\\s+\\S|[^\\s:#][^:]*:(\\s|$)|-(\\s|$)|#|\\s*$)')

def yaml_front_matter(lines: list) -> int:
    """首行起的 YAML front matter 行数（含首尾分隔线）；不是则返回 0。"""
    if not lines or lines[0].strip() != '---':
        return 0
    for (i, line) in enumerate(lines[1:], start=1):
        if line.strip() in ('---', '...'):
            return i + 1 if i > 1 else 0
        if not YAML_LINE_RE.match(line):
            return 0
    return 0

def is_metadata_header(lines: list) -> int:
    """返回从第 0 行起的元数据行数。

    OCR 工具典型元数据：
        # OCR Result
        # Characters: 123456
        # Date: 2026-...
        ---

    只有当开头的连续 `#`/`---`/空行块里包含 `---` 分隔线时，才视为元数据；
    否则当作正文（避免把 `# 开篇` 这种章节标题误吞）。

    Markdown 编辑器常见的 YAML front matter（首行 `---`，以 `---` 或 `...`
    收尾，中间均为 YAML 形态的行）整体视为元数据；中间出现正文形态的行
    则不认作 front matter，避免把以分隔线开头的正文整段吞掉。
    """
    yaml_end = yaml_front_matter(lines)
    if yaml_end:
        return yaml_end
    end = 0
    has_separator = False
    for (i, line) in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('---') and len(stripped.replace('-', '')) == 0:
            end = i + 1
            has_separator = True
            break
        if stripped.startswith('#') or stripped == '':
            continue
        break
    return end if has_separator else 0

def number_text(text: str) -> tuple[str, int]:
    text = text.translate(CTRL_CHARS)
    lines = text.split('\n')
    meta_end = is_metadata_header(lines)
    body_lines = lines[meta_end:]
    blocks = []
    cur = []
    pending_blank = False
    SENT_END_SET = set(SENT_END) | {'）', ')', '"', '”', '』', '」', '"', '】'}
    for ln in body_lines:
        if ln.strip() == '':
            if cur:
                pending_blank = True
            continue
        if is_heading_line(ln):
            if cur:
                blocks.append(cur)
                cur = []
            blocks.append([ln])
            pending_blank = False
            continue
        if pending_blank:
            last = cur[-1].rstrip() if cur else ''
            last_char = last[-1] if last else ''
            if last_char in SENT_END_SET:
                blocks.append(cur)
                cur = [ln]
            else:
                cur.append(ln)
            pending_blank = False
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    sentences = []
    for block in blocks:
        if len(block) == 1 and is_heading_line(block[0]):
            sentences.append(block[0].strip())
            continue
        idx = 0
        while idx < len(block) and is_heading_line(block[idx]):
            sentences.append(block[idx].strip())
            idx += 1
        if idx >= len(block):
            continue
        para = ''
        for ln in block[idx:]:
            para += ln
        para = re.sub('[ \\t]+', ' ', para).strip()
        sentences.extend(split_sentences(para))
    out_lines = []
    for (i, sent) in enumerate(sentences, start=1):
        out_lines.append(f'L{i:05d}: {sent}')
    return ('\n'.join(out_lines) + '\n', len(sentences))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source');p.add_argument('--output',required=True);p.add_argument('--source-id',required=True)
    a=p.parse_args(); out=check_output(a.output,[a.source]); meta=check_output(str(out)+'.meta.json',[a.source])
    content,count=number_text(read(a.source))
    if not count: raise ValueError('输入没有正文')
    metadata={'source_id':a.source_id,'original':os.path.relpath(Path(a.source).resolve(),out.resolve().parent),
        'original_sha256':digest(a.source),'position_type':'sentence-lines','algorithm':'sentence-v3','segments':count}
    write_new(out,content); metadata['sha256']=digest(out);write_new(meta,encode(metadata))
    print(encode({'segments':count,'position_type':'sentence-lines'}),end='')
if __name__=='__main__': raise SystemExit(run(main))
