"""可选工具行为验证；依赖见 docs/optional-tools.md。"""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/extraction'));sys.path.insert(0,str(ROOT/'tools/research'))
import extract,ocr,search
from compare import compare
RAW=ROOT/'examples/getting-started/raw'

def gemini(text='测试文字',finish='STOP'):
    return {'candidates':[{'finishReason':finish,'content':{'parts':[{'text':text}]}}]}
def vision(text='测试文字'):return {'responses':[{'fullTextAnnotation':{'text':text}}]}
def response(text='线索',url='https://example.org/original'):
    return {'output':[{'type':'message','content':[{'type':'output_text','text':text,'annotations':[{'url':url,'title':'模拟来源'}]}]}]}

class Optional(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def cli(self,tool,*args):
        return subprocess.run([sys.executable,str(ROOT/tool),*map(str,args)],capture_output=True,encoding='utf-8',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'})
    def test_docx_order(self):
        rows,missing,_=extract.extract(RAW/'registration.docx')
        self.assertFalse(missing);self.assertEqual([r['kind'] for r in rows],['paragraph','table','paragraph'])
        self.assertIn('12包',rows[1]['text']);self.assertIn('暂不发放',rows[2]['text'])
    def test_docx_revision_views_and_unsupported(self):
        original=(RAW/'complex.docx').read_bytes()
        with self.assertRaisesRegex(ValueError,'revisions_require_view'):extract.extract(RAW/'complex.docx')
        rows,missing,details=extract.extract(RAW/'complex.docx','original');text=''.join(x['text'] for x in rows)
        self.assertIn('20分钟',text);self.assertNotIn('30分钟',text);self.assertIn('txbxContent',missing);self.assertEqual(missing['nested_tables'],1)
        rows,_,_=extract.extract(RAW/'complex.docx','accepted');self.assertIn('30分钟',''.join(x['text'] for x in rows))
        self.assertEqual((RAW/'complex.docx').read_bytes(),original)
    def test_pdf_all_pages_and_states(self):
        rows,_,_=extract.extract(RAW/'mixed.pdf')
        self.assertEqual([r['position'] for r in rows],['page/1','page/2','page/3'])
        self.assertEqual([r['status'] for r in rows],['success','needs_ocr','empty_needs_review'])
    def test_pdf_two_columns_keep_content_order(self):
        import fitz
        doc=fitz.open();page=doc.new_page()
        for i in range(3):page.insert_text((40,100+i*40),f'左栏第{i+1}句。',fontname='china-s')
        for i in range(3):page.insert_text((320,104+i*40),f'右栏第{i+1}句。',fontname='china-s')
        doc.save(self.d/'two.pdf');doc.close()
        rows,_,details=extract.extract(self.d/'two.pdf')
        self.assertEqual(rows[0]['text'].split(),[f'左栏第{i}句。' for i in (1,2,3)]+[f'右栏第{i}句。' for i in (1,2,3)])
        self.assertEqual(details['text_order'],'content_stream')
    def test_slides_and_spreadsheets(self):
        rows,_,_=extract.extract(RAW/'brief.pptx');self.assertIn('菜豆',''.join(r['text'] for r in rows));self.assertEqual(len(rows),2)
        rows,_,_=extract.extract(RAW/'counts.xlsx');c=next(r for r in rows if r['position']=='清点!B3');self.assertEqual(c['formula'],'=B2+1');self.assertIsNone(c['cached_value'])
        rows,_,_=extract.extract(RAW/'legacy.xls');self.assertTrue(any(r['position']=='清点!R2C2' and r['text']=='12.0' for r in rows))
    def test_extract_status_exit_and_output_protection(self):
        out=self.d/'out';r=self.cli('tools/extraction/extract.py',RAW/'mixed.pdf','--output',out);self.assertEqual(r.returncode,3,r.stderr)
        before=(out/'report.json').read_bytes();r=self.cli('tools/extraction/extract.py',RAW/'registration.docx','--output',out);self.assertNotEqual(r.returncode,0);self.assertEqual(before,(out/'report.json').read_bytes())
        r=self.cli('tools/extraction/extract.py',RAW/'complex.docx','--output',self.d/'fail');self.assertEqual(r.returncode,1)
    def test_missing_dependency_is_failure(self):
        import builtins
        original=builtins.__import__
        def missing(name,*a,**kw):
            if name=='xlrd':raise ImportError('missing',name='xlrd')
            return original(name,*a,**kw)
        with patch('builtins.__import__',side_effect=missing):
            with self.assertRaises(ImportError):extract.extract(RAW/'legacy.xls')
    def test_ocr_response_validation(self):
        self.assertEqual(ocr.response_text('gemini',gemini()),'测试文字');self.assertEqual(ocr.response_text('cloud-vision',vision()),'测试文字')
        for engine,data in [('gemini',gemini('', 'STOP')),('gemini',gemini('部分','MAX_TOKENS')),('gemini',{'error':{}}),('gemini',{'name':'operations/1'}),('cloud-vision',{'responses':[]}),('cloud-vision',{'responses':[{'error':{'code':400}}]}),('cloud-vision',vision(''))]:
            with self.subTest(engine=engine,data=data):
                with self.assertRaises(ValueError):ocr.response_text(engine,data)
    def test_ocr_partial_resume_and_version_binding(self):
        out=self.d/'ocr';data={'1':gemini('第一页'),'2':gemini('残页','MAX_TOKENS'),'3':gemini('')}
        report=ocr.run(RAW/'mixed.pdf',out,'gemini',None,100,'teaching',['zh-Hans'],responses=data)
        self.assertEqual(report['status'],'partial');first=(out/'p0001.txt').stat().st_mtime_ns
        data['1']=gemini('不应替换');data['2']=gemini('第二页');report=ocr.run(RAW/'mixed.pdf',out,'gemini',None,100,'teaching',['zh-Hans'],True,data)
        self.assertEqual((out/'p0001.txt').read_text(encoding='utf-8'),'第一页');self.assertEqual((out/'p0001.txt').stat().st_mtime_ns,first);self.assertEqual(report['records'][1]['status'],'success')
        with self.assertRaisesRegex(ValueError,'changed'):ocr.run(RAW/'mixed.pdf',out,'gemini',[2],100,'teaching',['zh-Hans'],True,data)
        source=self.d/'changed.pdf';shutil.copy2(RAW/'mixed.pdf',source)
        with source.open('ab') as f:f.write(b'\n% changed version\n')
        with self.assertRaisesRegex(ValueError,'changed'):ocr.run(source,out,'gemini',None,100,'teaching',['zh-Hans'],True,data)
    def test_ocr_corrupt_cached_text_not_reused(self):
        out=self.d/'ocr';data={'1':gemini('原结果')};ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],responses=data)
        (out/'p0001.txt').write_text('被改过',encoding='utf-8');data={'1':gemini('有效新结果')};ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],True,data)
        self.assertEqual((out/'p0001.txt').read_text(encoding='utf-8'),'有效新结果')
    def test_ocr_no_implicit_network_or_overwrite(self):
        with patch('ocr.urlopen',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError,'execute'):ocr.run(RAW/'mixed.pdf',self.d/'none','gemini',None,100,'teaching',['zh-Hans'])
        self.assertFalse((self.d/'none').exists())
        out=self.d/'out';out.mkdir()
        with self.assertRaisesRegex(ValueError,'exists'):ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],responses={'1':gemini()})
    def test_compare_units_not_accuracy(self):
        f=self.d/'x.txt';f.write_text('一—'+'字'*98,encoding='utf-8');r=compare([f],['一—'],['字'])[0]
        self.assertEqual(r['patterns'][0]['per_10000_characters'],100);self.assertNotIn('accuracy',r);self.assertEqual(r['keyword_counts']['字'],98)
    def providers(self):
        return search.config(ROOT/'tools/research/providers.example.json',['doubao','qwen','qianfan','gemini'])
    def test_normalize_all_adapters(self):
        data=json.loads((ROOT/'examples/getting-started/search-responses.json').read_text(encoding='utf-8'));ps=self.providers()
        data['qianfan']={'choices':[{'finish_reason':'stop','message':{'content':'线索'}}],'references':[{'url':'https://example.org/baidu','title':'模拟'}]}
        for p in ps:
            r=search.normalize(p,'Q',data[p['id']]);self.assertEqual(r['status'],'success',r);self.assertFalse(r['evidence_eligible'])
    def test_search_no_sources_and_error_objects(self):
        p=self.providers()[0]
        for data in [{'error':{'message':'no'}},{'id':'accepted','status':'queued'},response('文本','not-a-url'),{},response(''),response(None),response({'not':'text'})]:
            self.assertNotEqual(search.normalize(p,'Q',data)['status'],'success')
    def test_missing_key_partial_all_failed_and_no_live_default(self):
        ps=self.providers()[:2]
        with patch.dict(os.environ,{},clear=True),patch('search.urlopen',side_effect=AssertionError('network')):
            r=search.execute(ps,'Q',self.d/'missing',live=True);self.assertEqual(r['status'],'no_usable_results');self.assertTrue(all(x['status']=='missing_key' for x in r['records']))
            with self.assertRaisesRegex(ValueError,'explicit'):search.execute(ps,'Q',self.d/'implicit')
        r=search.execute(ps,'Q',self.d/'partial',responses={'doubao':response()});self.assertEqual(r['status'],'partial')
    def test_same_source_native_import_and_no_overwrite(self):
        ps=self.providers()[:2];native=self.d/'native.json';native.write_text(json.dumps({'query':'Q','answer':'模拟','web_search_confirmed':True,'sources':[{'url':'https://example.org/reprint','origin':'https://example.org/original'}],'simulated':True}),encoding='utf-8')
        data={'doubao':response(),'qwen':response()};out=self.d/'out';r=search.execute(ps,'Q',out,responses=data,native_path=native)
        self.assertEqual(r['status'],'success');self.assertEqual(len(r['same_url_or_declared_origin_groups']['https://example.org/original']),3)
        with self.assertRaisesRegex(ValueError,'exists'):search.execute(ps,'Q',out,responses=data)
        self.assertEqual(search.native(native,'OTHER')['status'],'invalid_native_record')
    def test_search_resume_binding_and_valid_content(self):
        ps=self.providers()[:1];out=self.d/'out';search.execute(ps,'Q',out,responses={'doubao':response()})
        r=search.execute(ps,'Q',out,responses={},resume=True);self.assertEqual(r['status'],'success')
        with self.assertRaisesRegex(ValueError,'changed'):search.execute(ps,'OTHER',out,responses={},resume=True)
        file=out/'routes/doubao.json';data=json.loads(file.read_text(encoding='utf-8'));data['answer']='';file.write_text(json.dumps(data),encoding='utf-8')
        r=search.execute(ps,'Q',out,responses={},resume=True);self.assertEqual(r['status'],'no_usable_results')
    def test_redaction_and_proxy_preserved(self):
        sentinel='FAKE_TEST_TOKEN_NOT_A_KEY';p={**self.providers()[0],'model':'teaching'};before=dict(os.environ)
        with patch.dict(os.environ,{p['key_env']:sentinel}),patch('search.request',return_value=response(sentinel,'https://example.org/a?token='+sentinel)):
            search.execute([p],'Q',self.d/'redact',live=True)
        self.assertNotIn(sentinel,''.join(x.read_text(encoding='utf-8') for x in (self.d/'redact').rglob('*.json')));self.assertTrue(dict(os.environ)==before)
    def test_ocr_unknown_resume_requires_explicit_retry(self):
        out=self.d/'unknown'
        with patch.dict(os.environ,{'TEACHING_KEY':'FAKE_TEST_KEY'}),patch('ocr.cloud',side_effect=ValueError('request_result_unknown')) as call:
            ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],execute=True,key_env='TEACHING_KEY')
            self.assertEqual(call.call_count,1)
            ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],resume=True,execute=True,key_env='TEACHING_KEY')
            self.assertEqual(call.call_count,1)
            ocr.run(RAW/'mixed.pdf',out,'gemini',[1],100,'teaching',['zh-Hans'],resume=True,execute=True,key_env='TEACHING_KEY',retry_unknown=True)
            self.assertEqual(call.call_count,2)
    def test_search_unknown_resume_requires_explicit_retry(self):
        p={**self.providers()[0],'model':'teaching'};out=self.d/'unknown'
        with patch.dict(os.environ,{p['key_env']:'FAKE_TEST_KEY'}),patch('search.request',side_effect=ValueError('request_result_unknown')) as call:
            search.execute([p],'Q',out,live=True)
            search.execute([p],'Q',out,live=True,resume=True);self.assertEqual(call.call_count,1)
            search.execute([p],'Q',out,live=True,resume=True,retry_unknown=True);self.assertEqual(call.call_count,2)
    def test_finite_retries_and_unknown_not_retried(self):
        from urllib.error import HTTPError
        p={**self.providers()[0],'model':'teaching'}
        for module,invoke in [('search',lambda:search.request(p,'Q','FAKE_TEST_KEY',1,2)),('ocr',lambda:ocr.cloud('gemini',b'PNG','teaching','FAKE_TEST_KEY',1,2))]:
            with patch(module+'.urlopen',side_effect=HTTPError('https://example.org',429,'rate limit',None,None)) as call,patch(module+'.time.sleep'):
                with self.assertRaises(ValueError):invoke()
                self.assertEqual(call.call_count,3)
            with patch(module+'.urlopen',side_effect=TimeoutError()) as call:
                with self.assertRaisesRegex(ValueError,'unknown'):invoke()
                self.assertEqual(call.call_count,1)
    def test_arbitrary_ten_routes_and_concurrency(self):
        import threading
        base=self.providers()[0];rows=[{**base,'id':'route'+str(i)} for i in range(10)]
        c=self.d/'routes.json';c.write_text(json.dumps({'providers':rows}),encoding='utf-8')
        ps=search.config(c,[p['id'] for p in rows]);barrier=threading.Barrier(3)
        def normalized(p,q,data):
            if int(p['id'][5:])<3:barrier.wait(timeout=5)
            return {'provider':p['id'],'status':'success','answer':'simulated','sources':[{'url':'https://example.org/'+p['id']}]}
        with patch('search.normalize',side_effect=normalized):
            r=search.execute(ps,'Q',self.d/'ten',responses={},concurrency=3)
        self.assertEqual(len(r['records']),10);self.assertEqual(r['status'],'success')
        self.assertEqual([p['provider'] for p in r['records']],[p['id'] for p in ps])
    def test_deepseek_direct_search_and_multiple_imports(self):
        p=search.config(ROOT/'tools/research/providers.example.json',['deepseek'])[0]
        payload=search.build_payload(p,'教学问题');self.assertNotIn('model',payload)
        raw={'results':[{'url':'https://example.org/a','title':'模拟来源','summary':'模拟搜索摘要'}]}
        r=search.normalize(p,'Q',raw);self.assertEqual(r['status'],'success');self.assertFalse(r['evidence_eligible'])
        self.assertNotEqual(search.normalize(p,'Q',{'results':[]})['status'],'success')
        files=[]
        for name in ['kimi','another-search']:
            f=self.d/(name+'.json');f.write_text(json.dumps({'provider':name,'query':'Q','answer':'模拟','web_search_confirmed':True,'simulated':True,'sources':[{'url':'https://example.org/'+name}]}),encoding='utf-8');files.append(f)
        r=search.execute([],'Q',self.d/'imports',native_path=files)
        self.assertEqual(r['status'],'success');self.assertEqual([x['provider'] for x in r['records']],['kimi','another-search'])
    def test_help_preflight_do_not_request(self):
        r=self.cli('tools/research/search.py','--preflight','--routes','doubao');self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['status'],'preflight_only')
        for tool in ['tools/research/search.py','tools/extraction/ocr.py','tools/extraction/extract.py']:
            self.assertEqual(self.cli(tool,'--help').returncode,0)

if __name__=='__main__':unittest.main()
