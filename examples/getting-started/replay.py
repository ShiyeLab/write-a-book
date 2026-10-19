"""运行教学材料的机械步骤；预置正文与人工判断不由本脚本生成。"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from _common import encode,digest,sources
from verify_quotes import verify

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():p.error('输出已存在')
    a.output.mkdir(parents=True);records=[]
    def run(tool,args,expected=0):
        r=subprocess.run([sys.executable,str(ROOT/tool),*map(str,args)],capture_output=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        if r.returncode!=expected:raise RuntimeError(tool+' 未完成预期检查：'+r.stderr)
        records.append({'tool':tool,'returncode':r.returncode});return r
    raw=HERE/'raw';out=a.output
    run('tools/extraction/extract.py',[raw/'registration.docx',raw/'mixed.pdf',raw/'brief.pptx',raw/'counts.xlsx',raw/'legacy.xls',raw/'complex.docx','--revision-view','original','--output',out/'extract'],3)
    extraction=json.loads((out/'extract/report.json').read_text(encoding='utf-8'))
    assert extraction['records'][0]['status']=='success'
    assert [r['status'] for r in extraction['records'][1]['objects']]==['success','needs_ocr','empty_needs_review']
    assert extraction['records'][-1]['unsupported']['nested_tables']==1
    run('tools/research/search.py',['--query','教学：如何安排登记','--routes','doubao,qwen,qianfan,gemini','--responses',HERE/'search-responses.json','--native-record',HERE/'native-search.json','--output',out/'research'],3)
    # 按原有核心契约生成底本、清单、请求、卡片与索引。
    cards={}
    for version,name,location in [('v1','supplement-v1.txt','L2'),('v2','supplement-v2.txt','L3'),('new','new-note.txt','L2')]:
        folder=out/version;folder.mkdir()
        run('tools/inject_lines.py',[raw/name,'--source-id','S1' if version!='new' else 'S2','--output',folder/'lined.txt'])
        (folder/'sources.json').write_text(encode([{'id':'S1' if version!='new' else 'S2','path':'lined.txt','sha256':digest(folder/'lined.txt'),'position_type':'sentence-lines'}]),encoding='utf-8')
        (folder/'requests.json').write_text(encode([{'id':'Q1' if version!='new' else 'Q2','source_id':'S1' if version!='new' else 'S2','location':location,'source_kind':'teaching'}]),encoding='utf-8')
        run('tools/extract_quotes.py',[folder/'requests.json','--sources',folder/'sources.json','--output',folder/'cards.json'])
        run('tools/verify_quotes.py',[folder/'cards.json','--sources',folder/'sources.json'])
        run('tools/build_wiki.py',[folder/'cards.json','--output',folder/'wiki'])
        cards[version]=json.loads((folder/'cards.json').read_text(encoding='utf-8'))
    old_result=verify(cards['v1'],sources(out/'v2/sources.json'));assert old_result['passed']==0
    assert '20分钟' in cards['v1'][0]['quote'] and '30分钟' in cards['v2'][0]['quote']
    assert '南侧抽屉' not in cards['v1'][0]['quote'] and '南侧抽屉' in (raw/'supplement-v1.txt').read_text(encoding='utf-8')
    duplicate=out/'duplicate.txt';duplicate.write_bytes((raw/'supplement-v1.txt').read_bytes())
    register={digest(raw/'supplement-v1.txt'):'S1',digest(raw/'new-note.txt'):'S2'}
    duplicate_id=register.get(digest(duplicate))
    assert duplicate_id=='S1' and len(register)==2
    counts={p.name:len(re.findall('[\u4e00-\u9fff]',p.read_text(encoding='utf-8'))) for p in (HERE/'chapters').glob('*.md')}
    report={'status':'teaching_checks_passed','records':records,'ocr':'not_run; reference transcript is author-provided','research':'offline_simulation; not live search','extraction':extraction['status'],'old_version_rejected':True,'index_not_complete_source':True,'duplicate_source_id':duplicate_id,'registered_sources_after_duplicate':len(register),'chapter_basic_hanzi':counts,'total_basic_hanzi':sum(counts.values()),'author_feedback':'prewritten teaching decision; next task not executed'}
    (out/'report.json').write_text(encode(report),encoding='utf-8');print(encode(report))
if __name__=='__main__':main()
