"""按连续句级编号机械摘录，保留请求中的元数据。"""
import argparse
from _common import sources, indexed, json_read, excerpt, write_new, encode, check_output, run

def extract_all(requests, registry):
    indexed(requests)
    out=[]
    for row in requests:
        source=registry[row['source_id']]
        q=dict(row);q['quote']=excerpt(row['location'],source['_lines'])
        q['source_sha256']=source['sha256'];q['source_path']=source['path'];out.append(q)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('requests');p.add_argument('--sources',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();check_output(a.output,[a.requests,a.sources])
    out=extract_all(json_read(a.requests),sources(a.sources));write_new(a.output,encode(out));print('已摘录',len(out),'条')
if __name__=='__main__': raise SystemExit(run(main))
