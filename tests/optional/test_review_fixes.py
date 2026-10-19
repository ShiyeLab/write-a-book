"""复审发现的公式覆盖、缓存类型和续跑路径回归。"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date,datetime,time,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/extraction'))
sys.path.insert(0,str(ROOT/'tools/research'))
import extract,search

RAW=ROOT/'examples/getting-started/raw'
MATH='<m:oMath><m:r><m:t>x + y = z</m:t></m:r></m:oMath>'

def search_response(answer):
    return {'output':[{'type':'message','content':[{'type':'output_text','text':answer,
            'annotations':[{'url':'https://example.org/'+answer,'title':'教学来源'}]}]}]}

class ReviewFixes(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def cli(self,tool,*args):
        return subprocess.run([sys.executable,str(ROOT/tool),*map(str,args)],capture_output=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    def word(self,name,body):
        path=self.d/name
        document=('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                  'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>'
                  +body+'<w:sectPr/></w:body></w:document>').encode()
        with zipfile.ZipFile(RAW/'registration.docx') as source,zipfile.ZipFile(path,'w') as target:
            for info in source.infolist():
                target.writestr(info,document if info.filename=='word/document.xml' else source.read(info.filename))
        return path
    def test_math_in_paragraph_and_table_reports_partial_with_locations(self):
        source=self.word('equations.docx','<w:p><w:r><w:t>Formula:</w:t></w:r>'+MATH+'</w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table:</w:t></w:r><m:oMathPara>'+MATH+
            '</m:oMathPara></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>End.</w:t></w:r></w:p>')
        out=self.d/'output';result=self.cli('tools/extraction/extract.py',source,'--output',out)
        self.assertEqual(result.returncode,3,result.stderr)
        report=json.loads((out/'report.json').read_text(encoding='utf-8'));record=report['records'][0]
        self.assertEqual(record['status'],'partial');self.assertEqual(record['unsupported']['office_math'],2)
        self.assertEqual([(r['position'],r['kind'],r['office_math']) for r in record['unsupported_ranges']],
                         [('document.xml/body/1','paragraph',1),('document.xml/body/2','table',1)])
        self.assertEqual([r['status'] for r in record['objects']],['partial','partial','success'])
        text=(out/'0001.md').read_text(encoding='utf-8')
        for expected in ['Formula:','Table:','End.']:self.assertIn(expected,text)
        self.assertNotIn('x + y = z',text)
    def test_math_without_usable_body_fails(self):
        for name,body in [('paragraph','<w:p>'+MATH+'</w:p>'),
                          ('table','<w:tbl><w:tr><w:tc><w:p>'+MATH+'</w:p></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl>')]:
            with self.subTest(kind=name):
                source=self.word(name+'.docx',body);out=self.d/(name+'-out')
                result=self.cli('tools/extraction/extract.py',source,'--output',out)
                self.assertEqual(result.returncode,1,result.stderr)
                report=json.loads((out/'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['status'],'failed');self.assertEqual(report['records'][0]['unsupported']['office_math'],1)
    def test_cache_temporal_types_and_ordinary_values(self):
        values=[(date(2026,10,19),'date','2026-10-19'),
                (datetime(2026,10,19,12,30,tzinfo=timezone.utc),'datetime','2026-10-19T12:30:00+00:00'),
                (time(12,30,1,123456),'time','12:30:01.123456'),
                (timedelta(days=2,seconds=3,microseconds=4),'timedelta',{'days':2,'seconds':3,'microseconds':4}),
                (timedelta(microseconds=-1),'timedelta',{'days':-1,'seconds':86399,'microseconds':999999})]
        for value,kind,encoded in values:
            with self.subTest(kind=kind):
                result=extract.cached_value_fields(value)
                self.assertEqual(result,{'cached_value':encoded,'cached_type':kind})
                self.assertEqual(json.loads(json.dumps(result)),result)
        for value in [None,True,False,0,12,3.5,'text']:
            result=extract.cached_value_fields(value)
            self.assertEqual(result,{'cached_value':value});self.assertIs(type(result['cached_value']),type(value))
        with self.assertRaises(TypeError):extract.cached_value_fields(object())
    def spreadsheet(self):
        from openpyxl import Workbook
        from openpyxl.utils.datetime import to_excel
        file=self.d/'cached.xlsx';book=Workbook();sheet=book.active;sheet.title='Cache'
        specs={'A1':('=DATE(2026,10,19)','yyyy-mm-dd','n',str(to_excel(datetime(2026,10,19)))),
               'B1':('=TIME(12,0,0)','hh:mm:ss','n','0.5'),
               'C1':('=36/24','[h]:mm:ss','n','1.5'),
               'D1':('=1+2.5','General','n','3.5'),
               'E1':('=TRUE()','General','b','1'),
               'F1':('="saved"','General','str','saved'),
               'G1':('=1+1','General','n',None)}
        for position,(formula,format_,_,_) in specs.items():
            sheet[position]=formula;sheet[position].number_format=format_
        book.save(file)
        with zipfile.ZipFile(file) as z:entries=[(info,z.read(info.filename)) for info in z.infolist()]
        namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        with zipfile.ZipFile(file,'w') as z:
            for info,data in entries:
                if info.filename=='xl/worksheets/sheet1.xml':
                    root=ET.fromstring(data)
                    for cell in root.iter(namespace+'c'):
                        _,_,kind,value=specs[cell.attrib['r']];cell.set('t',kind);cell.find(namespace+'v').text=value
                    data=ET.tostring(root)
                z.writestr(info,data)
        return file
    def test_saved_excel_values_and_mixed_batch(self):
        file=self.spreadsheet();out=self.d/'batch'
        result=self.cli('tools/extraction/extract.py',file,RAW/'registration.docx','--output',out)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads((out/'report.json').read_text(encoding='utf-8'));self.assertEqual([x['status'] for x in report['records']],['success','success'])
        cells={r['position']:r for r in report['records'][0]['objects']}
        self.assertEqual((cells['Cache!A1']['cached_value'],cells['Cache!A1']['cached_type']),('2026-10-19T00:00:00','datetime'))
        self.assertEqual((cells['Cache!B1']['cached_value'],cells['Cache!B1']['cached_type']),('12:00:00','time'))
        self.assertEqual((cells['Cache!C1']['cached_value'],cells['Cache!C1']['cached_type']),({'days':1,'seconds':43200,'microseconds':0},'timedelta'))
        self.assertEqual([cells['Cache!'+p]['cached_value'] for p in ['D1','E1','F1','G1']],[3.5,True,'saved',None])
        self.assertIs(cells['Cache!E1']['cached_value'],True)
        for p in ['D1','E1','F1','G1']:self.assertNotIn('cached_type',cells['Cache!'+p])
        self.assertEqual(cells['Cache!A1']['formula'],'=DATE(2026,10,19)')
        self.assertEqual(cells['Cache!A1']['text'],'=DATE(2026,10,19)')
        self.assertIn('12包',(out/'0002.md').read_text(encoding='utf-8'))
    def run_batch(self,out):
        args=['extract.py',str(RAW/'registration.docx'),str(RAW/'registration.docx'),str(RAW/'registration.docx'),'--output',str(out)]
        with patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):return extract.main()
    def test_report_serialization_failure_preserves_progress_and_continues(self):
        original=extract.extract;calls=[]
        def input_result(*args):
            calls.append(True);rows,missing,details=original(*args)
            if len(calls)==2:details['unsupported_test_value']=object()
            return rows,missing,details
        out=self.d/'serialization'
        with patch('extract.extract',side_effect=input_result):result=self.run_batch(out)
        self.assertEqual(result,3);self.assertEqual(len(calls),3)
        report=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual([r['status'] for r in report['records']],['success','failed','success'])
        self.assertEqual(report['records'][1]['error'],'report_write_failed')
        self.assertTrue((out/'0001.md').is_file());self.assertTrue((out/'0003.md').is_file())
    def test_report_io_failure_keeps_previous_snapshot_and_continues(self):
        original=extract.save;calls=[];preserved=[];out=self.d/'io-failure'
        def write(path,data):
            calls.append(True)
            if len(calls)==2:
                previous=(out/'report.json').read_bytes();Path(path).write_text('incomplete',encoding='utf-8')
                preserved.append((out/'report.json').read_bytes()==previous)
                raise OSError('simulated write failure')
            return original(path,data)
        with patch('extract.save',side_effect=write):result=self.run_batch(out)
        self.assertEqual(result,3);self.assertEqual(preserved,[True])
        report=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual([r['status'] for r in report['records']],['success','failed','success'])
        self.assertEqual(report['records'][1]['error'],'report_write_failed');self.assertFalse((out/'report.tmp').exists())
    def test_persistent_report_failure_returns_error_and_keeps_completed_snapshot(self):
        original=extract.save;calls=[];out=self.d/'persistent'
        def write(path,data):
            calls.append(True)
            if len(calls)>1:raise OSError('simulated persistent write failure')
            return original(path,data)
        with patch('extract.save',side_effect=write),contextlib.redirect_stderr(io.StringIO()) as stderr:result=self.run_batch(out)
        self.assertEqual(result,1);self.assertIn('report_write_failed',stderr.getvalue())
        report=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual([r['status'] for r in report['records']],['success','not_processed','not_processed'])
        self.assertTrue((out/'0003.md').is_file())
    def providers(self):
        base=search.config(ROOT/'tools/research/providers.example.json',['doubao'])[0]
        return [{**base,'id':name,'model':'teaching'} for name in ['binding','report','regular']]
    def test_reserved_route_names_parallel_resume_without_request(self):
        providers=self.providers();out=self.d/'search'
        with patch.dict(os.environ,{providers[0]['key_env']:'FAKE_TEST_KEY'},clear=True),patch('search.request',side_effect=lambda p,*args:search_response(p['id'])) as request:
            first=search.execute(providers,'Q',out,live=True,concurrency=3)
            self.assertEqual(first['status'],'success');self.assertEqual(request.call_count,3)
            cached={p['id']:((out/'routes'/(p['id']+'.json')).read_bytes(),(out/'routes'/(p['id']+'.json')).stat().st_mtime_ns) for p in providers}
            binding=(out/'binding.json').read_bytes();request.reset_mock()
            second=search.execute(providers,'Q',out,live=True,resume=True,concurrency=2)
            self.assertEqual(second['status'],'success');request.assert_not_called()
        self.assertEqual((out/'binding.json').read_bytes(),binding)
        self.assertEqual(json.loads(binding)['layout_version'],2)
        self.assertEqual([r['answer'] for r in second['records']],['binding','report','regular'])
        for name,(data,mtime) in cached.items():
            self.assertEqual((out/'routes'/(name+'.json')).read_bytes(),data)
            self.assertEqual((out/'routes'/(name+'.json')).stat().st_mtime_ns,mtime)
        self.assertEqual(json.loads((out/'report.json').read_text(encoding='utf-8'))['status'],'success')
    def test_legacy_search_layout_rejected_before_request_or_write(self):
        providers=self.providers()
        for name in ['binding','report','regular']:
            with self.subTest(route=name):
                out=self.d/name;out.mkdir()
                (out/'binding.json').write_text(json.dumps({'algorithm':'search-v2'}),encoding='utf-8')
                (out/(name+'.json')).write_text(json.dumps({'provider':name,'status':'success','answer':'saved','sources':[{'url':'https://example.org/a'}]}),encoding='utf-8')
                before={p.name:p.read_bytes() for p in out.iterdir()}
                with patch('search.request',side_effect=AssertionError('request must not run')) as request:
                    with self.assertRaisesRegex(ValueError,'unsupported_output_layout_use_new_directory'):
                        search.execute(providers,'Q',out,live=True,resume=True)
                    request.assert_not_called()
                self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},before)
        config=self.d/'config.json';config.write_text(json.dumps({'providers':providers}),encoding='utf-8')
        r=self.cli('tools/research/search.py','--config',config,'--routes','regular','--query','Q','--output',self.d/'regular','--execute','--resume')
        self.assertEqual(r.returncode,1);self.assertIn('请使用新输出目录',r.stderr)

if __name__=='__main__':unittest.main()
