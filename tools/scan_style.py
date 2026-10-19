"""生成文风编辑建议，输入稿件保持不变。"""
import argparse
import json
import re
from pathlib import Path
from _common import read,write_new,check_output,encode,run

def rules_from(path):
    blocks=re.findall(r'```json\n(.*?)\n```',read(path),re.S)
    if len(blocks)!=1: raise ValueError('规则文件须包含一个 JSON 代码块')
    rows=json.loads(blocks[0])
    from _common import indexed
    indexed(rows,'规则')
    for row in rows:
        if row.get('kind') not in ['literal','regex']: raise ValueError('未知规则类型')
        pattern=row['pattern']
        if not isinstance(pattern,str) or not pattern: raise ValueError('规则不能为空')
        try: row['_compiled']=re.compile(pattern if row['kind']=='regex' else re.escape(pattern))
        except re.error as e: raise ValueError('规则正则无效') from e
    return rows

def scan(text,rules,include_quotes=False):
    hits=[];skipped=[];fence=None;exception=False
    for n,line in enumerate(text.splitlines(),1):
        f=re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$',line)
        if fence:
            skipped.append(n)
            if f and f[1][0]==fence[0] and len(f[1])>=len(fence) and not f[2].strip(): fence=None
            continue
        if f: fence=f[1];skipped.append(n);continue
        if line.strip()=='<!-- style:off -->': exception=True;skipped.append(n);continue
        if line.strip()=='<!-- style:on -->': exception=False;skipped.append(n);continue
        if exception or (not include_quotes and re.match(r'^\s*>',line)):
            skipped.append(n);continue
        for row in rules:
            for m in row['_compiled'].finditer(line):
                hits.append({'line':n,'column':m.start()+1,'rule':row['id'],'suggestion':row['suggestion']})
    if exception or fence: raise ValueError('代码围栏或 style:off 未闭合')
    return {'kind':'编辑建议，不判断作者来源','hits':hits,'skipped_lines':skipped,'author_baseline':'未提供，不计算密度阈值'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--rules',default=str(Path(__file__).with_name('style_rules.md')));p.add_argument('--output',required=True);p.add_argument('--include-quotes',action='store_true')
    a=p.parse_args();check_output(a.output,[a.input,a.rules]);r=scan(read(a.input),rules_from(a.rules),a.include_quotes);write_new(a.output,encode(r));print('建议',len(r['hits']),'处；未修改输入')
if __name__=='__main__':raise SystemExit(run(main))
