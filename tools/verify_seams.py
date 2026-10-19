"""剥离独立标记行后精确比较，接缝与补写分别计数。"""
import argparse
import re
from _common import read,encode,run
MARK=re.compile(r'^【(接缝|补写|补)[:：][^\r\n]*】[ \t]*$')

def verify(marked,baseline):
    kept=[];seams=additions=0
    for line in marked.split('\n'):
        m=MARK.fullmatch(line)
        if not m: kept.append(line)
        elif m[1]=='接缝': seams+=1
        else: additions+=1
    equal='\n'.join(kept)==baseline
    return {'equal_after_stripping':equal,'seam_lines':seams,'addition_lines':additions,
        'meaning':'补写属于新增文字；一致只证明剥离标记后等于纯删节稿'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('marked');p.add_argument('baseline');a=p.parse_args()
    report=verify(read(a.marked),read(a.baseline));print(encode(report),end='');return int(not report['equal_after_stripping'])
if __name__=='__main__':raise SystemExit(run(main))
