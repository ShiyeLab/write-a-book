"""用完整素材和独立标签建立条目、主题及关键词索引。"""
import argparse
import os
import tempfile
import shutil
from pathlib import Path
from urllib.parse import quote as urlquote
from collections import defaultdict
from _common import indexed, json_read, encode, check_output, run

def filename(value):
    # 百分号也编码，避免两个不同 ID 清理后变成同名文件。
    return urlquote(value,safe='')+'.md'

def link_name(name):
    return urlquote(name,safe='')

def check_filenames(names,label):
    seen={}
    for name in names:
        generated=filename(name);folded=generated.casefold()
        if folded in seen and seen[folded]!=name:
            other=seen[folded]
            raise ValueError(f'{label}文件名大小写冲突：{other!r} ({filename(other)}) 与 {name!r} ({generated})')
        seen[folded]=name

def build(cards,tags,output):
    rows=indexed(cards);meta=indexed(tags,'标签') if tags else {}
    if set(meta)-set(rows): raise ValueError('分类 ID 找不到完整原文')
    for row in rows.values():
        if not isinstance(row.get('quote'),str) or not row['quote'].strip(): raise ValueError('缺完整原文: '+row['id'])
        for key in ['source_id','location']:
            if not isinstance(row.get(key),str) or not row[key]: raise ValueError('缺 '+key)
    for m in meta.values():
        if set(m)-{'id','topics','keywords','related_ids','summary','title'}: raise ValueError('标签含未支持字段；正文不能放在分类文件')
        for field in ['topics','keywords','related_ids']:
            v=m.get(field,[])
            if not isinstance(v,list) or any(not isinstance(x,str) or not x.strip() for x in v): raise ValueError('标签列表无效')
        if set(m.get('related_ids',[]))-set(rows): raise ValueError('关联 ID 不存在')
    check_filenames(rows,'条目')
    check_filenames((topic for rid in rows for topic in (meta.get(rid,{}).get('topics',[]) or ['未分类'])),'主题')
    out=check_output(output);out.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.wiki-',dir=out.parent))
    try:
        (stage/'entries').mkdir();(stage/'topics').mkdir(); topics=defaultdict(list);keywords=defaultdict(list)
        for rid,row in rows.items():
            m=meta.get(rid,{})
            for topic in m.get('topics',[]) or ['未分类']: topics[topic].append(rid)
            for kw in m.get('keywords',[]): keywords[kw].append(rid)
            # 正文原样追加在固定分隔符后，末尾不另补换行。
            header='# 素材 '+rid+'\n\n来源：'+row['source_id']+'；位置：'+row['location']+'\n\n'
            if m.get('summary'): header+='摘要（非原文）：'+m['summary']+'\n\n'
            if m.get('related_ids'): header+='关联：'+', '.join('['+x+']('+link_name(filename(x))+')' for x in m['related_ids'])+'\n\n'
            (stage/'entries'/filename(rid)).write_text(header+'<!-- full-quote -->\n'+row['quote'],encoding='utf-8')
        top=['# 素材索引','',f'独立素材 {len(rows)} 条。主题视图只链接到正式条目。','']
        for topic,ids in sorted(topics.items()):
            name=filename(topic);top.append('['+topic+'](topics/'+link_name(name)+')')
            (stage/'topics'/name).write_text('# '+topic+'\n\n'+'\n'.join('- ['+i+'](../entries/'+link_name(filename(i))+')' for i in ids)+'\n',encoding='utf-8')
        (stage/'README.md').write_text('\n\n'.join(top)+'\n',encoding='utf-8')
        (stage/'cards.json').write_text(encode(cards),encoding='utf-8')
        (stage/'keywords.json').write_text(encode(dict(keywords)),encoding='utf-8')
        (stage/'index.json').write_text(encode({k:'entries/'+filename(k) for k in rows}),encoding='utf-8')
        if out.exists(): raise ValueError('输出已存在')
        os.rename(stage,out)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return {'entries':len(rows),'topics':len(topics)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cards');p.add_argument('--tags');p.add_argument('--output',required=True)
    a=p.parse_args();print(encode(build(json_read(a.cards),json_read(a.tags) if a.tags else [],a.output)),end='')
if __name__=='__main__': raise SystemExit(run(main))
