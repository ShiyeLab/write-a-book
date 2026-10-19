"""离线重放机械步骤；不调用模型，不重新生成示范正文。"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from _common import encode,write_new,check_output

def cli(tool,*args,report=None):
    result=subprocess.run([sys.executable,str(ROOT/'tools'/tool),*map(str,args)],encoding='utf-8',capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    if result.returncode: raise RuntimeError(tool+': '+result.stderr+result.stdout)
    if report:write_new(report,result.stdout)
    return result.stdout

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('example',choices=['source-based','true-stories','abridgement','polishing']);p.add_argument('--output',required=True);a=p.parse_args()
    src=ROOT/'examples'/a.example;out=check_output(a.output);out.mkdir(parents=True)
    if a.example in ['source-based','true-stories']:
        names=['desk','form','review'] if a.example=='source-based' else ['a','b'];sources=[]
        for name in names:
            target=out/'lined'/f'{name}.txt'
            cli('inject_lines.py',src/'raw'/f'{name}.txt','--output',target,'--source-id',name)
            sources.append({'id':name,'path':f'lined/{name}.txt','position_type':'sentence-lines','sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        write_new(out/'sources.json',encode(sources))
        cli('extract_quotes.py',src/'requests.json','--sources',out/'sources.json','--output',out/'cards.json')
        cli('verify_quotes.py',out/'cards.json','--sources',out/'sources.json',report=out/'quote-report.json')
        if a.example=='source-based':
            cli('build_wiki.py',out/'cards.json','--tags',src/'tags.json','--output',out/'wiki')
            cli('verify_style_sources.py',src/'style/evidence.json','--samples',src/'style/samples',report=out/'style-report.json')
            cli('build_wiki.py',src/'long-fixtures.json','--output',out/'long-wiki')
            originals=json.loads((src/'long-fixtures.json').read_text(encoding='utf-8'))
            from build_wiki import filename
            for row in originals:
                body=(out/'long-wiki/entries'/filename(row['id'])).read_text(encoding='utf-8').split('<!-- full-quote -->\n',1)[1]
                if body!=row['quote']:raise ValueError('长摘录未完整保存')
            write_new(out/'long-report.json',encode({'lengths':[len(x['quote']) for x in originals],'full_text_equal':True,'final_newline_in_quote':[x['quote'].endswith('\n') for x in originals]}))
    elif a.example=='abridgement':
        cli('apply_cuts.py',src/'cuts.json','--base',src,'--output',out/'pure.md','--report',out/'counts.json','--require-budget')
        pure=(out/'pure.md').read_text(encoding='utf-8');needle='白岩收好纸张'
        marked=pure.replace(needle,'【接缝：下段放回铅笔的动作，早先铺垫已删；请判断是否恢复。】\n【补写：登记台的铅笔也收了起来。】\n'+needle,1)
        write_new(out/'marked.md',marked)
        cli('verify_seams.py',out/'marked.md',out/'pure.md',report=out/'seam-report.json')
    elif a.example=='polishing':
        original=(src/'original.md').read_text(encoding='utf-8');revised=(src/'revised.md').read_text(encoding='utf-8')
        if original.split('\n\n',2)[2]!=revised.split('\n\n',2)[2]:raise ValueError('首段以外有变化')
        for token in ['12张','周栩','蓝色条纹','地址']:
            if token not in revised:raise ValueError('保留项缺失')
        cli('scan_style.py',src/'revised.md','--output',out/'style-report.json')
        write_new(out/'preservation-report.json',encode({'unchanged_after_first_paragraph':True,'required_tokens_present':True,'scope':'文本块与字面信息；首段语义见 preservation.md 的人工阅读记录'}))
    print('运行示例完成：'+a.example)
if __name__=='__main__':main()
