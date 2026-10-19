"""逐页 Apple Vision／Gemini／Cloud Vision OCR；默认不调用云服务。"""
import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from extract import sha,save,status,code,write_lf

PROMPT='逐字转录这一页全部文字，保留段落；不解释不补写。看不清处标为[待核]。空白页不要编写文字。'

def response_text(engine,data):
    if not isinstance(data,dict) or data.get('error') is not None:raise ValueError('service_error')
    if engine=='gemini':
        candidates=data.get('candidates') or []
        if not candidates:raise ValueError('missing_candidate')
        c=candidates[0]
        if c.get('finishReason')!='STOP':raise ValueError('incomplete_response')
        text='\n'.join(p['text'] for p in c.get('content',{}).get('parts',[]) if isinstance(p.get('text'),str) and not p.get('thought'))
    else:
        rows=data.get('responses')
        if not isinstance(rows,list) or len(rows)!=1:raise ValueError('page_response_mismatch')
        if rows[0].get('error') is not None:raise ValueError('page_error')
        text=rows[0].get('fullTextAnnotation',{}).get('text','')
    if not isinstance(text,str) or not text.strip():raise ValueError('empty_response')
    return text

def cloud(engine,png,model,key,timeout,retries):
    image=base64.b64encode(png).decode()
    if engine=='gemini':
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        body={'contents':[{'parts':[{'inline_data':{'mime_type':'image/png','data':image}},{'text':PROMPT}]}],'generationConfig':{'temperature':0,'maxOutputTokens':8192}}
    else:
        url='https://vision.googleapis.com/v1/images:annotate'
        body={'requests':[{'image':{'content':image},'features':[{'type':'DOCUMENT_TEXT_DETECTION'}],'imageContext':{'languageHints':['zh-Hans','en']}}]}
    request=Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key})
    for attempt in range(retries+1):
        try:
            with urlopen(request,timeout=timeout) as r:data=json.load(r)
            return response_text(engine,data)
        except HTTPError as e:
            # 仅已明确拒绝的限流允许有限重试；未知提交结果不重发。
            if e.code==429 and attempt<retries:time.sleep(min(2**attempt,4));continue
            raise ValueError('http_'+str(e.code)) from None
        except (ValueError,KeyError,TypeError) as e:
            if isinstance(e,ValueError) and str(e) in ['service_error','missing_candidate','incomplete_response','page_response_mismatch','page_error','empty_response']:raise
            raise ValueError('invalid_response') from None
        except Exception:raise ValueError('request_result_unknown') from None

def run(source,output,engine,pages,dpi,model,language,resume=False,responses=None,execute=False,key_env=None,timeout=60,retries=0,retry_unknown=False):
    import fitz
    if not source.is_file():raise ValueError('input_missing')
    if engine=='apple' and sys.platform!='darwin':raise ValueError('apple_requires_macos')
    if not 72<=dpi<=600 or not 1<=timeout<=180 or not 0<=retries<=2:raise ValueError('invalid_limits')
    if engine=='gemini' and not re.fullmatch(r'[A-Za-z0-9._-]+',model or ''):raise ValueError('explicit_model_required')
    if responses is not None and execute:raise ValueError('choose_offline_or_live')
    key=''
    if engine!='apple' and responses is None:
        if not execute:raise ValueError('cloud_requires_execute')
        if not key_env or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key_env):raise ValueError('explicit_key_env_required')
        key=os.environ.get(key_env,'')
        if not key:raise ValueError('selected_key_ABSENT')
    if engine=='apple':
        from ocrmac import ocrmac
    doc=fitz.open(source)
    try:
        selected=sorted(set(pages or range(1,len(doc)+1)))
        if not selected or selected[0]<1 or selected[-1]>len(doc):raise ValueError('invalid_page_range')
        binding={'input_sha256':sha(source),'pages':selected,'engine':engine,'dpi':dpi,'model':model,'languages':language,'mode':'offline_fixture' if responses is not None else 'actual','algorithm':'page-ocr-v1','prompt':PROMPT}
        if output.exists():
            if not resume:raise ValueError('output_exists')
            if json.loads((output/'binding.json').read_text(encoding='utf-8'))!=binding:raise ValueError('resume_input_or_parameters_changed')
        else:output.mkdir(parents=True);save(output/'binding.json',binding)
        records=[]
        for n in range(1,len(doc)+1):
            if n not in selected:records.append({'page':n,'status':'not_processed'});continue
            print(f'page {n}/{len(doc)}',flush=True)
            text_path=output/f'p{n:04}.txt';record_path=output/f'p{n:04}.json'
            if resume and record_path.exists():
                old=json.loads(record_path.read_text(encoding='utf-8'))
                if old.get('error')=='request_result_unknown' and not retry_unknown:records.append(old);continue
                if old.get('status')=='success' and text_path.exists() and old.get('text_sha256')==sha(text_path) and text_path.read_text(encoding='utf-8').strip():records.append(old);continue
            try:
                png=doc[n-1].get_pixmap(dpi=dpi).tobytes('png')
                if responses is not None:text=response_text(engine,responses.get(str(n),{}))
                elif engine=='apple':
                    with tempfile.NamedTemporaryFile(suffix='.png',dir=output) as f:
                        f.write(png);f.flush()
                        observations=ocrmac.OCR(f.name,framework='vision',language_preference=language,recognition_level='accurate').recognize()
                        text='\n'.join(x[0] for x in observations)
                else:text=cloud(engine,png,model,key,timeout,retries)
                if not text.strip():raise ValueError('empty_response')
                if key:text=text.replace(key,'[REDACTED]')
                write_lf(text_path,text)
                rec={'page':n,'status':'success','file':text_path.name,'text_sha256':sha(text_path),'quality':'not_reviewed'}
            except Exception as e:
                allowed=['service_error','missing_candidate','incomplete_response','page_response_mismatch','page_error','empty_response','request_result_unknown','invalid_response']
                reason=str(e) if isinstance(e,ValueError) and (str(e) in allowed or re.fullmatch(r'http_\d{3}',str(e))) else 'ocr_failed'
                rec={'page':n,'status':'empty_needs_review' if reason=='empty_response' else 'failed','error':reason}
                # 续跑时旧内容若不再有效，从合并正文中排除，留旧文件供人工诊断。
            save(record_path,rec);records.append(rec)
            save(output/'report.json',{'status':status(records+[{'status':'not_processed'} for _ in range(n,len(doc))]),'total_pages':len(doc),'processed_through':n,'records':records+[{'page':i,'status':'not_processed'} for i in range(n+1,len(doc)+1)],'quality':'not_reviewed','mode':binding['mode']})
        report={'status':status(records),'total_pages':len(doc),'records':records,'quality':'not_reviewed','mode':binding['mode']}
        save(output/'report.json',report)
        write_lf(output/'text.md','\n\n'.join(f"<!-- page {r['page']} [{r['status']}] -->\n"+((output/r['file']).read_text(encoding='utf-8') if r['status']=='success' else '') for r in records)+'\n')
        return report
    finally:doc.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--engine',required=True,choices=['apple','gemini','cloud-vision']);p.add_argument('--pages',help='物理页序，例如 1,2,4');p.add_argument('--dpi',type=int,default=200);p.add_argument('--model');p.add_argument('--languages',default='zh-Hans,en-US');p.add_argument('--resume',action='store_true');p.add_argument('--responses',type=Path,help='仅离线模拟：页序到响应对象的 JSON');p.add_argument('--execute',action='store_true');p.add_argument('--key-env');p.add_argument('--timeout',type=float,default=60);p.add_argument('--retries',type=int,default=0);p.add_argument('--retry-unknown',action='store_true',help='仅在查明可安全重试后显式启用');a=p.parse_args()
    try:
        report=run(a.input,a.output,a.engine,[int(x) for x in a.pages.split(',')] if a.pages else None,a.dpi,a.model,a.languages.split(','),a.resume,json.loads(a.responses.read_text(encoding='utf-8')) if a.responses else None,a.execute,a.key_env,a.timeout,a.retries,a.retry_unknown)
        print(report['status']);return code(report['status'])
    except ImportError:print('缺可选依赖：按 docs/optional-tools.md 安装 PyMuPDF；Apple 路线另需 ocrmac。',file=sys.stderr);return 1
    except Exception as e:
        known={'input_missing','apple_requires_macos','invalid_limits','explicit_model_required','choose_offline_or_live','cloud_requires_execute','explicit_key_env_required','selected_key_ABSENT','invalid_page_range','output_exists','resume_input_or_parameters_changed'}
        print(str(e) if isinstance(e,ValueError) and str(e) in known else '配置、输入或续跑记录无效',file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
