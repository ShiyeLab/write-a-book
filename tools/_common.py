"""文本工具共用的文件、数据与位置检查。"""
import json
import os
import re
import sys
import tempfile
import hashlib
from pathlib import Path

def read(path):
    return Path(path).read_text(encoding='utf-8')

def json_read(path):
    return json.loads(read(path))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def encode(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'

def check_output(path, inputs=()):
    p=Path(path)
    if any(p.resolve()==Path(i).resolve() for i in inputs):
        raise ValueError('输出不能覆盖输入')
    if p.exists() or p.is_symlink():
        raise ValueError('输出已存在，请使用新路径')
    return p

def write_new(path, text):
    p=check_output(path); p.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=p.parent, prefix='.writing-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f: f.write(text)
        # 硬链接使目标存在时失败，避免覆盖并发写入。
        os.link(tmp,p)
    finally:
        os.unlink(tmp)

def indexed(rows, label='条目'):
    if not isinstance(rows,list) or not rows: raise ValueError(label+'必须是非空数组')
    result={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'].strip():
            raise ValueError(label+'缺少非空 id')
        if row['id'] in result: raise ValueError(label+'重复 id: '+row['id'])
        result[row['id']]=row
    return result

def interval(value):
    if not isinstance(value,str): raise ValueError('位置必须是 L 起止字符串')
    m=re.fullmatch(r'L(\d+)(?:-L(\d+))?',value)
    if not m: raise ValueError('位置只支持单行或一个连续闭区间')
    a=int(m[1]); b=int(m[2] or m[1])
    if a<1 or b<a: raise ValueError('位置倒置或小于 1')
    return a,b

def lined(path):
    result={}
    for line in read(path).split('\n'):
        if line=='': continue
        m=re.fullmatch(r'L(\d+): ?(.*)',line)
        if not m: raise ValueError('带行号底本含无编号行')
        n=int(m[1])
        if n<1 or n in result: raise ValueError('底本行号无效或重复')
        result[n]=m[2]
    if not result: raise ValueError('底本没有行号')
    return result

def excerpt(ref, lines):
    a,b=interval(ref)
    if b>max(lines): raise ValueError('引用越界')
    if any(i not in lines for i in range(a,b+1)): raise ValueError('引用包含缺失行')
    text=''.join(lines[i] for i in range(a,b+1))
    if not text.strip(): raise ValueError('摘录为空')
    return text

def sources(path):
    result=indexed(json_read(path),'来源')
    base=Path(path).resolve().parent
    for row in result.values():
        rel=row.get('path')
        if not isinstance(rel,str) or not rel or Path(rel).is_absolute(): raise ValueError('来源 path 必须为相对路径')
        p=base/rel
        if row.get('sha256')!=digest(p): raise ValueError('来源版本不符: '+row['id'])
        if row.get('position_type')!='sentence-lines': raise ValueError('仅支持声明为 sentence-lines 的底本')
        row['_lines']=lined(p)
    return result

def run(main):
    try:
        code=main()
        return code or 0
    except (OSError,ValueError,KeyError,TypeError,IndexError) as e:
        print('错误: '+str(e),file=sys.stderr)
        return 1
