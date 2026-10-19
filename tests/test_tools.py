"""验证数据保全、错误返回和跨目录运行。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from _common import lined,excerpt,sources,digest,encode,indexed
from inject_lines import number_text
from extract_quotes import extract_all
from verify_quotes import verify as quotes_verify
from build_wiki import build,filename
from apply_cuts import apply
from verify_seams import verify as seams_verify
from verify_style_sources import verify as style_verify
from scan_style import scan,rules_from

class Tools(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='中文 空格 ');self.d=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def put(self,name,text):
        p=self.d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return p
    def cli(self,name,*args):
        return subprocess.run([sys.executable,str(ROOT/'tools'/name),*map(str,args)],cwd=self.d,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'},capture_output=True,encoding='utf-8')
    def fixture(self):
        p=self.put('lined.txt','L00001: 开始。\nL00002: 尾部无换行')
        registry={'S':{'id':'S','path':'lined.txt','sha256':digest(p),'position_type':'sentence-lines','_lines':lined(p)}}
        rows=extract_all([{'id':'Q','source_id':'S','location':'L1-L2','attribution':'待确认'}],registry)
        return registry,rows
    def test_inject_sentence_boundaries(self):
        text,count=number_text('# 标题\n\n他说：“可以。再试！”然后走了。\n\n尾句无标点')
        self.assertEqual(count,4)
        self.assertIn('L00002: 他说：“可以。再试！”',text)
        self.assertIn('L00004: 尾句无标点',text)
    def test_inject_headings_without_blank_lines(self):
        expected='L00001: # 总题\nL00002: 第一段。\nL00003: ## 小节\nL00004: 第二段。\n'
        for separator in ['\n','\n\n']:
            with self.subTest(separator=repr(separator)):
                self.assertEqual(number_text(separator.join(['# 总题','第一段。','## 小节','第二段。'])),(expected,4))
    def test_inject_consecutive_and_middle_headings(self):
        self.assertEqual(number_text('前文未收句\n# 一级\n## 二级\n后文续\n行。'),
                         ('L00001: 前文未收句\nL00002: # 一级\nL00003: ## 二级\nL00004: 后文续行。\n',4))
    def test_inject_ordinary_continuation(self):
        self.assertEqual(number_text('普通续\n行。\n下一句\n\n继续。'),
                         ('L00001: 普通续行。\nL00002: 下一句继续。\n',2))
    def test_inject_legacy_spacing_and_metadata(self):
        text,count=number_text('# OCR\n---\n\n# 标题\n\n未完\n\n续句。 下一句！')
        self.assertEqual(count,3);self.assertNotIn('OCR',text);self.assertIn('未完续句。',text)
    def test_inject_apostrophe_is_not_quote(self):
        text,count=number_text("It's late! Who's there? Nobody!")
        self.assertEqual(count,3);self.assertIn("L00002: Who's there?",text)
    def test_inject_yaml_front_matter(self):
        text,count=number_text('---\ntitle: 访谈记录\ntags:\n  - 口述\n---\n他说：“我记得。”然后走了。')
        self.assertEqual(text,'L00001: 他说：“我记得。”\nL00002: 然后走了。\n')
        text,_=number_text('---\n第一段正文。\n---\n第二段正文。')
        self.assertIn('第一段正文。',text)
        text,_=number_text('---\ntitle: 未闭合\n正文。')
        self.assertIn('title: 未闭合',text)
    def test_inject_long_sentence_control_and_punctuation(self):
        source='测'*240
        out,count=number_text(source);self.assertEqual(count,3)
        self.assertEqual(''.join(x.split(': ',1)[1] for x in out.splitlines()),source)
        out,_=number_text('甲\x0c乙；丙。');self.assertIn('甲 乙；丙。',out)
    def test_inject_refuses_source_and_empty(self):
        src=self.put('raw.txt','保留原件。')
        before=src.read_bytes();r=self.cli('inject_lines.py',src,'--source-id','s','--output',src)
        self.assertNotEqual(r.returncode,0);self.assertEqual(before,src.read_bytes())
        src=self.put('empty.txt','');r=self.cli('inject_lines.py',src,'--source-id','s','--output',self.d/'new')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.d/'new').exists())
    def test_full_quotes_and_metadata(self):
        reg,rows=self.fixture();self.assertEqual(rows[0]['quote'],'开始。尾部无换行')
        self.assertEqual(rows[0]['attribution'],'待确认');self.assertEqual(quotes_verify(rows,reg)['passed'],1)
    def test_changed_truncated_empty_wrong_source(self):
        reg,rows=self.fixture()
        for value in ['开始。尾部无换形','开始。尾部','']:
            with self.subTest(value=value):
                x=copy.deepcopy(rows);x[0]['quote']=value;self.assertEqual(quotes_verify(x,reg)['passed'],0)
        for key,val in [('source_id','missing'),('source_sha256','wrong'),('source_path','wrong'),('location','L9')]:
            x=copy.deepcopy(rows);x[0][key]=val;self.assertEqual(quotes_verify(x,reg)['passed'],0)
    def test_zero_and_duplicate_ids_fail(self):
        for rows in [[],[{'id':'x'},{'id':'x'}],[{}]]:
            with self.assertRaises(ValueError):indexed(rows)
    def test_missing_lines_and_invalid_range(self):
        p=self.put('s','L00001: 甲\nL00003: 乙')
        for ref in ['L1-L3','L0','L3-L1','L1,L3','L100']:
            with self.assertRaises(ValueError):excerpt(ref,lined(p))
        for text in ['L1: 甲\nL1: 乙','L0: 甲','无编号','']:
            self.put('s',text)
            with self.assertRaises(ValueError):lined(p)
    def test_sources_version_missing_and_type(self):
        src=self.put('s','L1: 甲');spec=[{'id':'S','path':'s','sha256':digest(src),'position_type':'sentence-lines'}]
        manifest=self.put('sources.json',encode(spec));self.assertEqual(len(sources(manifest)),1)
        for key,value in [('sha256','bad'),('path','absent'),('position_type','physical-lines')]:
            row=copy.deepcopy(spec);row[0][key]=value;manifest.write_text(encode(row),encoding='utf-8')
            with self.assertRaises((ValueError,OSError)):sources(manifest)
    def test_extract_cli_errors_write_nothing(self):
        req=self.put('request.json','[]');manifest=self.put('sources.json','[]')
        r=self.cli('extract_quotes.py',req,'--sources',manifest,'--output',self.d/'out')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.d/'out').exists())
    def test_wiki_long_no_newline_and_no_truncation(self):
        rows=json.loads((ROOT/'examples/source-based/long-fixtures.json').read_text(encoding='utf-8'))
        self.assertGreater(len(rows[0]['quote']),500);self.assertGreater(len(rows[1]['quote']),5000)
        build(rows,[],self.d/'wiki')
        for row in rows:
            actual=(self.d/'wiki/entries'/filename(row['id'])).read_text(encoding='utf-8').split('<!-- full-quote -->\n',1)[1]
            self.assertEqual(actual,row['quote']);self.assertFalse(actual.endswith('\n'))
    def test_wiki_bad_inputs_no_partial(self):
        row={'id':'x','source_id':'s','location':'L1','quote':'全文'}
        cases=[([row,row],[]),([{'id':'x'}],[]),([row],[{'id':'missing'}]),([row],[{'id':'x','quote':'摘要'}]),([row],[{'id':'x','related_ids':['none']}])]
        for rows,tags in cases:
            with self.assertRaises(ValueError):build(rows,tags,self.d/'wiki')
            self.assertFalse((self.d/'wiki').exists())
    def test_wiki_id_filenames_distinct(self):
        rows=[{'id':i,'source_id':'s','location':'L1','quote':'全文'} for i in ['x/y','x%2Fy','x_y']]
        build(rows,[],self.d/'wiki');self.assertEqual(len(list((self.d/'wiki/entries').glob('*.md'))),3)
    def test_wiki_readable_unicode_names_and_lf(self):
        rows=[{'id':i,'source_id':'s','location':'L1','quote':'第一行\n第二行'} for i in ['素材一','.隐藏']]
        tags=[{'id':'素材一','topics':['来源核对']}]
        build(rows,tags,self.d/'wiki');out=self.d/'wiki'
        self.assertTrue((out/'topics'/'来源核对.md').is_file());self.assertTrue((out/'entries'/'%2E隐藏.md').is_file())
        self.assertIn('(topics/来源核对.md)',(out/'README.md').read_text(encoding='utf-8'))
        self.assertNotIn(b'\r\n',(out/'entries'/'素材一.md').read_bytes())
        with self.assertRaisesRegex(ValueError,'名称过长'):
            build(rows,[{'id':'素材一','topics':['长'*90]}],self.d/'long')
        self.assertFalse((self.d/'long').exists())
    def assert_wiki_collision(self,ids,topics,conflicts):
        rows=[{'id':rid,'source_id':'s','location':'L1','quote':'完整文字：'+rid} for rid in ids]
        tags=[{'id':rid,'topics':[topic]} for rid,topic in zip(ids,topics)]
        cards=self.put('cards.json',encode(rows));labels=self.put('tags.json',encode(tags))
        before=(cards.read_bytes(),labels.read_bytes())
        with self.assertRaisesRegex(ValueError,'大小写.*冲突') as error:
            build(rows,tags,self.d/'wiki')
        for name in conflicts:self.assertIn(name,str(error.exception))
        result=self.cli('build_wiki.py',cards,'--tags',labels,'--output',self.d/'wiki')
        self.assertNotEqual(result.returncode,0)
        for name in conflicts:self.assertIn(name,result.stderr)
        self.assertEqual(before,(cards.read_bytes(),labels.read_bytes()))
        self.assertFalse((self.d/'wiki').exists());self.assertEqual(list(self.d.glob('.wiki-*')),[])
    def test_wiki_rejects_case_colliding_ids(self):
        self.assert_wiki_collision(['M01','m01'],[],['M01','m01'])
    def test_wiki_rejects_case_colliding_topics(self):
        self.assert_wiki_collision(['M01','M02'],['Topic','topic'],['Topic','topic'])
    def test_wiki_shared_topic_and_separate_directories(self):
        from urllib.parse import unquote
        import re
        rows=[{'id':rid,'source_id':'s','location':'L1','quote':'完整原文：'+rid} for rid in ['Topic','M02']]
        tags=[{'id':row['id'],'topics':['topic'],'keywords':['共享'],'related_ids':[rows[1-i]['id']]} for i,row in enumerate(rows)]
        out=self.d/'wiki';self.assertEqual(build(rows,tags,out),{'entries':2,'topics':1})
        index=json.loads((out/'index.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((out/'keywords.json').read_text(encoding='utf-8')),{'共享':['Topic','M02']})
        topic=out/'topics'/filename('topic')
        for row in rows:
            entry=out/index[row['id']]
            self.assertEqual(entry.name,filename(row['id']))
            self.assertEqual(entry.read_text(encoding='utf-8').split('<!-- full-quote -->\n',1)[1],row['quote'])
            self.assertIn('['+row['id']+']',topic.read_text(encoding='utf-8'))
        for page in [topic]+list((out/'entries').glob('*.md')):
            links=re.findall(r'\]\(([^)]+)\)',page.read_text(encoding='utf-8'));self.assertTrue(links)
            for link in links:self.assertTrue((page.parent/unquote(link)).is_file())
    def test_cuts_replay(self):
        spec={'range':[1,4],'cuts':[{'start':2,'end':2},{'line':3,'drop':'中间'}],'budget':10}
        result,r=apply('标题\n删除\n左中间右\n末尾',spec)
        self.assertEqual(result,'标题\n左右\n末尾\n');self.assertEqual(r['deleted_hanzi'],4)
    def test_cuts_invalid_no_output(self):
        source=self.put('source.txt','甲甲甲\n乙');out=self.d/'out'
        for cuts in [[{'line':1,'drop':''}],[{'line':1,'drop':'甲甲'}],[{'start':0,'end':1}],[{'line':9,'drop':'乙'}],[{'wrong':1}]]:
            spec=self.put('cuts.json',encode({'source':'source.txt','range':[1,2],'cuts':cuts}))
            r=self.cli('apply_cuts.py',spec,'--base',self.d,'--output',out)
            self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
    def test_cuts_range_and_budget_fail(self):
        for rg in [[0,1],[1,99],[2,1],[True,2]]:
            with self.assertRaises(ValueError):apply('甲\n乙',{'range':rg,'cuts':[]})
        self.put('source.txt','甲乙');spec=self.put('cuts.json',encode({'source':'source.txt','range':[1,1],'cuts':[],'budget':1}))
        r=self.cli('apply_cuts.py',spec,'--base',self.d,'--output',self.d/'out','--require-budget')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.d/'out').exists())
    def test_seams_split_counts_and_exactness(self):
        baseline='甲\n乙\n';marked='甲\n【接缝：检查】\n【补写：新增】\n乙\n'
        r=seams_verify(marked,baseline);self.assertTrue(r['equal_after_stripping']);self.assertEqual((r['seam_lines'],r['addition_lines']),(1,1))
        self.assertFalse(seams_verify(marked.replace('乙','丙'),baseline)['equal_after_stripping'])
        self.assertFalse(seams_verify('甲【接缝：内联】\n乙\n',baseline)['equal_after_stripping'])
        self.assertFalse(seams_verify(marked.rstrip('\n'),baseline)['equal_after_stripping'])
    def test_style_strict_normalized_location_and_empty(self):
        self.put('sample.txt','“可以……”\n第二行\n第三行\n第四行\n第五行')
        card={'id':'e','file':'sample.txt','lines':[1,1],'quote':'"可以"'}
        self.assertEqual(style_verify([card],self.d)['passed'],0)
        self.assertEqual(style_verify([card],self.d,'normalized')['passed'],1)
        for key,value in [('quote','不可以'),('file','missing'),('lines',[5,5]),('quote','…')]:
            c={**card,key:value};self.assertEqual(style_verify([c],self.d,'normalized')['passed'],0)
        with self.assertRaises(ValueError):style_verify([],self.d)
    def test_scan_exclusions_and_no_modification(self):
        text='普通——正文\n> 引文——保留\n```text\n代码——保留\n```\n<!-- style:off -->\n例外——保留\n<!-- style:on -->\n'
        source=self.put('draft.md',text);before=source.read_bytes();r=self.cli('scan_style.py',source,'--output',self.d/'report.json')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(before,source.read_bytes())
        report=json.loads((self.d/'report.json').read_text(encoding='utf-8'));self.assertEqual(len(report['hits']),1);self.assertEqual(report['hits'][0]['line'],1)
        r=self.cli('scan_style.py',source,'--output',source);self.assertNotEqual(r.returncode,0);self.assertEqual(before,source.read_bytes())
    def test_scan_bad_rules_and_unclosed_regions(self):
        rule=self.put('rules.md','```json\n[]\n```')
        with self.assertRaises(ValueError):rules_from(rule)
        rules=rules_from(ROOT/'tools/style_rules.md')
        for text in ['```\n文本','<!-- style:off -->\n文本']:
            with self.assertRaises(ValueError):scan(text,rules)
    def test_failure_cli_returns_nonzero(self):
        empty=self.put('empty.json','[]')
        for tool,args in [('verify_style_sources.py',[empty,'--samples',self.d]),('verify_quotes.py',[empty,'--sources',empty]),('build_wiki.py',[empty,'--output',self.d/'wiki'])]:
            r=self.cli(tool,*args);self.assertNotEqual(r.returncode,0)
    def test_all_examples_from_other_cwd(self):
        for name in ['source-based','true-stories','abridgement','polishing']:
            r=subprocess.run([sys.executable,str(ROOT/'examples/replay.py'),name,'--output',str(self.d/name)],cwd=self.d,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'},capture_output=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,name+r.stderr)

if __name__=='__main__':unittest.main()
