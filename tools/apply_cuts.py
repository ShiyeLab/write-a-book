"""重放整行及唯一子串删除，先校验全部请求再写稿。"""
import argparse
import re
from pathlib import Path
from _common import read,json_read,write_new,encode,check_output,run

def hz(text): return len(re.findall(r'[一-鿿]',text))

def integer(v): return isinstance(v,int) and not isinstance(v,bool)

def apply(text,spec):
    src=text.split('\n');a,b=spec['range']
    if not integer(a) or not integer(b) or not 1<=a<=b<=len(src): raise ValueError('原文范围越界')
    if not isinstance(spec.get('cuts'),list): raise ValueError('cuts 必须为数组')
    bud=spec.get('budget')
    if bud is not None and (not integer(bud) or bud<=0): raise ValueError('预算必须为正整数')
    lines={i:src[i-1] for i in range(a,b+1)};orig=hz('\n'.join(lines.values()));cut=0
    for c in spec['cuts']:
        if 'start' in c and 'line' not in c:
            s,e=c['start'],c['end']
            if not integer(s) or not integer(e) or not a<=s<=e<=b: raise ValueError('删除区间越界')
            for i in range(s,e+1):
                if i in lines: cut+=hz(lines.pop(i))
        elif 'line' in c and 'start' not in c:
            i,sub=c['line'],c['drop']
            if not integer(i) or i not in lines: raise ValueError('行内删除越界或行已删除')
            if not isinstance(sub,str) or not sub or '\n' in sub: raise ValueError('删除子串必须为非空单行文本')
            # count() 不计算重叠命中，逐起点计数才能拒绝歧义。
            hits=sum(lines[i].startswith(sub,j) for j in range(len(lines[i])))
            if hits!=1: raise ValueError('删除子串必须唯一命中')
            cut+=hz(sub);lines[i]=lines[i].replace(sub,'',1)
        else: raise ValueError('未知删节操作')
    result=re.sub(r'\n{3,}','\n\n','\n'.join(lines.values())).strip()+'\n'
    kept=hz(result)
    return result,{'original_hanzi':orig,'deleted_hanzi':cut,'kept_hanzi':kept,'budget':bud,
        'over_budget':bud is not None and kept>bud,'budget_delta':kept-bud if bud else None,
        'counting':'U+4E00—U+9FFF；包含范围内标题和注记'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cuts');p.add_argument('--base',required=True);p.add_argument('--output',required=True);p.add_argument('--report');p.add_argument('--require-budget',action='store_true')
    a=p.parse_args();spec=json_read(a.cuts);rel=Path(spec['source'])
    if rel.is_absolute(): raise ValueError('source 必须是相对 base 的路径')
    source=Path(a.base)/rel;check_output(a.output,[source,a.cuts])
    if a.report:
        check_output(a.report,[source,a.cuts,a.output])
    result,report=apply(read(source),spec)
    if a.require_budget and (report['budget'] is None or report['over_budget']): raise ValueError('预算缺失或超限，未写稿')
    write_new(a.output,result)
    if a.report: write_new(a.report,encode(report))
    print(encode(report),end='')
if __name__=='__main__': raise SystemExit(run(main))
