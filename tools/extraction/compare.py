"""OCR 可疑模式与关键词对照；没有人工参考时不计算准确率。"""
import argparse,json,re
from pathlib import Path

def compare(paths,patterns,keywords):
    result=[]
    for path in paths:
        text=path.read_text(encoding='utf-8');length=len(text)
        result.append({'file':path.name,'characters':length,'patterns':[{'pattern':p,'hits':len(re.findall(p,text)),'per_10000_characters':len(re.findall(p,text))/length*10000 if length else None} for p in patterns],'keyword_counts':{k:text.count(k) for k in keywords},'interpretation':'可疑模式密度和关键词命中，不是错字率或真实准确率'})
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',nargs='+',type=Path);p.add_argument('--pattern',action='append',default=[]);p.add_argument('--keyword',action='append',default=[]);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():p.error('输出已存在')
    try:data=compare(a.inputs,a.pattern or ['—一|一—','[，。、；：！？]{3,}'],a.keyword)
    except (OSError,re.error):p.error('输入或正则无效')
    with a.output.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
