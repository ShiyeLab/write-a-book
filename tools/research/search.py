"""显式选路的可选检索；预检和离线响应回放不会发请求。"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from adapters import build_payload,normalize_response,utc_now

ADAPTERS={'deepseek_search','responses_annotations','responses_action_sources','qianfan_ai_search','gemini_grounding'}

def safe_url(value):
    try:
        u=urlsplit(value)
        if u.scheme not in ['http','https'] or not u.hostname or u.username or u.password:return ''
        query=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if not re.search('key|token|auth|secret|signature|password|credential',k,re.I)]
        return urlunsplit((u.scheme,u.netloc,u.path,urlencode(query),''))
    except (ValueError,TypeError):return ''

def clean(value,secrets):
    if isinstance(value,str):
        for secret in secrets:
            if secret:value=value.replace(secret,'[REDACTED]')
        value=re.sub(r'(?i)(Bearer\s+)\S+',r'\1[REDACTED]',value)
        return value
    if isinstance(value,list):return [clean(x,secrets) for x in value]
    if isinstance(value,dict):return {k:clean(v,secrets) for k,v in value.items() if not re.search('authorization|api.?key|cookie|token|secret',k,re.I)}
    return value

def normalize(provider,query,raw):
    if not isinstance(raw,dict) or raw.get('error') is not None:return {'provider':provider['id'],'status':'invalid_response','answer':'','sources':[]}
    try:record=normalize_response(provider,query,raw)
    except (TypeError,KeyError,IndexError,AttributeError):return {'provider':provider['id'],'status':'invalid_response','answer':'','sources':[]}
    incomplete=raw.get('status') in ['queued','in_progress','incomplete','failed','cancelled']
    if provider['adapter']=='gemini_grounding':incomplete=incomplete or (raw.get('candidates') or [{}])[0].get('finishReason')!='STOP'
    if provider['adapter']=='qianfan_ai_search':incomplete=incomplete or (raw.get('choices') or [{}])[0].get('finish_reason') not in ['stop','normal']
    sources=[];seen=set()
    for src in record['sources']:
        url=safe_url(src['url'])
        if url and url not in seen:seen.add(url);sources.append({**src,'url':url})
    record['sources']=sources
    if incomplete:record['status']='incomplete_response'
    elif record['status']=='success' and not sources:record['status']='no_sources'
    record['evidence_eligible']=False
    record['limitations']=['仅检索线索；必须打开直接来源并人工判断独立性、范围和可引用性。']
    # 不保存 usage 或其他未经限制的服务字段，也不存原始响应。
    return {k:record[k] for k in ['provider','status','answer','sources','limitations','evidence_eligible']}

def request(provider,query,key,timeout,retries):
    endpoint=provider['endpoint'].replace('{model}',provider.get('model',''))
    u=urlsplit(endpoint)
    if u.scheme!='https' or u.query or u.username or u.password:raise ValueError('invalid_endpoint')
    headers={'Content-Type':'application/json'}
    headers['x-goog-api-key' if provider['adapter']=='gemini_grounding' else 'Authorization']=key if provider['adapter']=='gemini_grounding' else 'Bearer '+key
    req=Request(endpoint,data=json.dumps(build_payload(provider,query)).encode(),headers=headers)
    for attempt in range(retries+1):
        try:
            with urlopen(req,timeout=timeout) as r:return json.load(r)
        except HTTPError as e:
            if e.code==429 and attempt<retries:time.sleep(min(2**attempt,4));continue
            raise ValueError('http_'+str(e.code)) from None
        except Exception:raise ValueError('request_result_unknown') from None

def config(path,routes):
    rows=json.loads(path.read_text(encoding='utf-8'))['providers'];mapping={}
    for row in rows:
        if not re.fullmatch('[a-z0-9_-]+',row.get('id','')) or row['id'] in mapping:raise ValueError('invalid_route_id')
        if row.get('adapter') not in ADAPTERS:raise ValueError('invalid_adapter')
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',row.get('key_env','')):raise ValueError('one_key_env_required')
        if set(row)-{'id','adapter','key_env','model','endpoint','tools','search_source','top_k','deep_search'}:raise ValueError('unknown_config_field')
        u=urlsplit(row.get('endpoint',''))
        if u.scheme!='https' or not u.hostname or u.query or u.username or u.password:raise ValueError('invalid_endpoint')
        mapping[row['id']]=row
    if not routes or len(set(routes))!=len(routes) or set(routes)-set(mapping):raise ValueError('select_known_routes')
    return [mapping[n] for n in routes]

def native(path,query):
    data=json.loads(path.read_text(encoding='utf-8'));sources=[]
    for row in data.get('sources',[]):
        url=safe_url(row.get('url',''))
        if url:sources.append({'url':url,'title':str(row.get('title','')),'origin':safe_url(row.get('origin',''))})
    okay=data.get('query')==query and data.get('web_search_confirmed') is True and isinstance(data.get('answer'),str) and bool(data['answer'].strip()) and bool(sources)
    return {'provider':data.get('provider','host-native-import'),'status':'success' if okay else 'invalid_native_record','answer':data.get('answer','') if okay else '', 'sources':sources if okay else [],'evidence_eligible':False,'simulated':bool(data.get('simulated',False))}

def execute(providers,query,out,live=False,responses=None,native_path=None,resume=False,timeout=60,retries=0,retry_unknown=False,concurrency=1):
    if live and responses is not None:raise ValueError('choose_offline_or_live')
    if not 1<=timeout<=180 or not 0<=retries<=2 or not isinstance(concurrency,int) or concurrency<1:raise ValueError('invalid_limits')
    if not live and responses is None and not native_path:raise ValueError('explicit_execution_or_offline_input_required')
    imports=native_path if isinstance(native_path,list) else [native_path] if native_path else []
    binding={'query':query,'providers':providers,'mode':'live' if live else 'offline','native_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in imports],'algorithm':'search-v2','layout_version':2}
    # 配置只允许变量名，绑定文件不记录凭证值。
    if out.exists():
        if not resume:raise ValueError('output_exists')
        try:old_binding=json.loads((out/'binding.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):raise ValueError('unsupported_output_layout_use_new_directory') from None
        if not isinstance(old_binding,dict) or old_binding.get('layout_version')!=2 or not (out/'routes').is_dir():raise ValueError('unsupported_output_layout_use_new_directory')
        if old_binding!=binding:raise ValueError('resume_input_or_config_changed')
    else:
        out.mkdir(parents=True);(out/'routes').mkdir();write(out/'binding.json',binding)
    secrets=[os.environ.get(p['key_env'],'') for p in providers] if live else []
    records=[{'provider':p['id'],'status':'not_processed','answer':'','sources':[]} for p in providers]
    def one(p):
        file=out/'routes'/(p['id']+'.json')
        if resume and file.exists():
            old=json.loads(file.read_text(encoding='utf-8'));signature=old.pop('_record_sha256',None)
            if old.get('status')=='request_result_unknown' and not retry_unknown:return old
            if signature==fingerprint(old) and old.get('status')=='success' and old.get('sources') and old.get('answer'):return old
        try:
            if responses is not None:record=normalize(p,query,responses.get(p['id'],{}))
            elif not live:record={'provider':p['id'],'status':'not_run','answer':'','sources':[]}
            elif not os.environ.get(p['key_env']):record={'provider':p['id'],'status':'missing_key','key_env':p['key_env'],'presence':'ABSENT','answer':'','sources':[]}
            elif p['adapter']!='deepseek_search' and not p.get('model'):record={'provider':p['id'],'status':'model_required','answer':'','sources':[]}
            else:record=normalize(p,query,request(p,query,os.environ[p['key_env']],timeout,retries))
        except ValueError as e:
            reason=str(e) if re.fullmatch(r'http_\d{3}',str(e)) or str(e) in ['invalid_search_query','invalid_search_count'] else 'request_result_unknown'
            record={'provider':p['id'],'status':reason,'answer':'','sources':[]}
        except Exception:record={'provider':p['id'],'status':'request_result_unknown','answer':'','sources':[]}
        record=clean(record,secrets);write(file,{**record,'_record_sha256':fingerprint(record)});return record
    def progress():
        pending=[{'provider':'import-'+str(i+1),'status':'not_processed','answer':'','sources':[]} for i in range(len(imports))]
        write(out/'report.json',{'status':'in_progress','mode':binding['mode'],'records':records+pending})
    progress()
    if providers:
        with ThreadPoolExecutor(max_workers=min(concurrency,len(providers))) as pool:
            futures={pool.submit(one,p):i for i,p in enumerate(providers)}
            for completed,future in enumerate(as_completed(futures),1):
                i=futures[future];records[i]=future.result()
                print(f'route {completed}/{len(providers)}: {providers[i]["id"]}',flush=True);progress()
    for p in imports:records.append(clean(native(p,query),secrets))
    groups={}
    for record in records:
        for src in record['sources']:groups.setdefault(src.get('origin') or src['url'],[]).append(record['provider'])
    usable=sum(r['status']=='success' for r in records)
    state='success' if usable==len(records) and usable else 'partial' if usable else 'no_usable_results'
    report={'status':state,'query':query,'mode':binding['mode'],'records':records,'same_url_or_declared_origin_groups':groups,'independence':'只按 URL／人工声明原始来源分组；不同网址仍可能同源，须人工复核','completed_at':utc_now()}
    write(out/'report.json',clean(report,secrets));return report

def fingerprint(record):return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=Path(__file__).with_name('providers.example.json'));p.add_argument('--routes',help='显式逗号分隔路线');p.add_argument('--preflight',action='store_true');p.add_argument('--query');p.add_argument('--output',type=Path);p.add_argument('--execute',action='store_true');p.add_argument('--responses',type=Path);p.add_argument('--native-record',type=Path,action='append',help='可重复指定不同工具的实际搜索记录');p.add_argument('--resume',action='store_true');p.add_argument('--timeout',type=float,default=60);p.add_argument('--retries',type=int,default=0);p.add_argument('--retry-unknown',action='store_true',help='查明服务端状态及重试安全后使用');p.add_argument('--concurrency',type=int,default=1,help='自行选择并发路线数；默认逐路，不限定路线总数');a=p.parse_args()
    try:
        providers=config(a.config,a.routes.split(',')) if a.routes else []
        if a.preflight:
            if not providers:p.error('预检须指定 --routes')
            rows=[{'route':x['id'],'variable':x['key_env'],'presence':'PRESENT' if os.environ.get(x['key_env']) else 'ABSENT','model_configured':bool(x.get('model'))} for x in providers]
            print(json.dumps({'status':'preflight_only','routes':rows},ensure_ascii=False));return 0
        if not a.query or not a.output or (not providers and not a.native_record):p.error('指定问题、输出及路线或原生记录')
        report=execute(providers,a.query,a.output,a.execute,json.loads(a.responses.read_text(encoding='utf-8')) if a.responses else None,a.native_record,a.resume,a.timeout,a.retries,a.retry_unknown,a.concurrency)
        print(report['status']);return {'success':0,'partial':3,'no_usable_results':1}[report['status']]
    except Exception as e:
        if isinstance(e,ValueError) and str(e)=='unsupported_output_layout_use_new_directory':
            print('输出目录为旧版或不完整布局，请使用新输出目录；原结果已保留。',file=sys.stderr);return 1
        known={'invalid_route_id','invalid_adapter','one_key_env_required','unknown_config_field','invalid_endpoint','select_known_routes','choose_offline_or_live','invalid_limits','explicit_execution_or_offline_input_required','output_exists','resume_input_or_config_changed'}
        print(str(e) if isinstance(e,ValueError) and str(e) in known else '配置或输入无效',file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
