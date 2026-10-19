"""检查证据引文在申报位置出现；严格或显式规范化模式。"""
import argparse
from pathlib import Path
from _common import json_read,indexed,read,encode,run
QMAP=str.maketrans({'“':'"','”':'"','‘':"'",'’':"'",'…':'','⋯':''})

def verify(cards,base,mode='strict',window=0):
    indexed(cards)
    if window<0: raise ValueError('window 不能为负')
    result=[]
    for card in cards:
        r={'id':card['id'],'matched':False}
        try:
            p=Path(card['file'])
            if p.is_absolute() or '..' in p.parts: raise ValueError('样本路径须在样本目录内')
            source=(Path(base)/p).resolve()
            if not source.is_relative_to(Path(base).resolve()): raise ValueError('样本不在样本目录内')
            lines=read(source).splitlines();a,b=card['lines']
            if type(a)!=int or type(b)!=int or not 1<=a<=b<=len(lines): raise ValueError('行号无效')
            q=card['quote']
            if not isinstance(q,str) or not q.strip(): raise ValueError('空引文')
            text='\n'.join(lines[max(0,a-1-window):min(len(lines),b+window)])
            if mode=='normalized': q=q.translate(QMAP);text=text.translate(QMAP)
            if not q.strip(): raise ValueError('规范化后引文为空')
            r['matched']=q in text
            if not r['matched']: r['error']='申报范围内未找到引文'
        except (ValueError,KeyError,OSError,TypeError) as e: r['error']=str(e)
        result.append(r)
    return {'mode':mode,'window':window,'check':'范围内子串定位，不证明整个摘录覆盖完整区间','total':len(result),'passed':sum(x['matched'] for x in result),'results':result}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cards');p.add_argument('--samples',required=True);p.add_argument('--mode',choices=['strict','normalized'],default='strict');p.add_argument('--window',type=int,default=0)
    a=p.parse_args();r=verify(json_read(a.cards),a.samples,a.mode,a.window);print(encode(r),end='');return int(r['passed']!=r['total'])
if __name__=='__main__': raise SystemExit(run(main))
