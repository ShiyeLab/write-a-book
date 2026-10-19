"""分别报告位置有效与完整摘录相等；不做近似匹配。"""
import argparse
from _common import sources, indexed, json_read, excerpt, encode, run

def verify(rows,registry):
    indexed(rows); results=[]
    for row in rows:
        item={'id':row['id'],'location_valid':False,'full_text_equal':False}
        try:
            src=registry[row['source_id']]
            if row.get('source_sha256')!=src['sha256'] or row.get('source_path')!=src['path']:
                raise ValueError('摘录的来源版本或路径不符')
            expected=excerpt(row['location'],src['_lines']);item['location_valid']=True
            item['full_text_equal']=isinstance(row.get('quote'),str) and row['quote']==expected
            if not item['full_text_equal']: item['error']='完整正文不同'
        except (KeyError,ValueError,TypeError) as e: item['error']=str(e)
        results.append(item)
    return {'total':len(results),'passed':sum(x['full_text_equal'] for x in results),'results':results}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cards');p.add_argument('--sources',required=True)
    a=p.parse_args();report=verify(json_read(a.cards),sources(a.sources));print(encode(report),end='')
    return int(report['passed']!=report['total'])
if __name__=='__main__': raise SystemExit(run(main))
