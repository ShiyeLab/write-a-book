import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {capture,publicUrl} from '../../tools/web-capture/capture.mjs';
import {runVlmCrossCheck,textFrom} from '../../tools/web-capture/vlm-bridge.mjs';
const dir=await fs.mkdtemp(path.join(os.tmpdir(),'book-web-'));
const originalEnv={...process.env};
const article='<html><title>Teaching</title><main><h1>教学页面</h1><p>'+('登记名称和数量，保留批次编号。'.repeat(15))+'</p></main></html>';
const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(req.url==='/empty'?'<html><body></body></html>':req.url==='/login'?'<html><body>请登录后继续阅读<article>'+('会员专享内容。'.repeat(30))+'</article></body></html>':article);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
// 受控本地页面测试显式设置旁路，仅测试进程使用；被测模块不改环境。
process.env.NO_PROXY='127.0.0.1';process.env.no_proxy='127.0.0.1';const during={...process.env};
const browser=process.env.BOOK_TEST_BROWSER;
try {
  let r=await capture({url:base+'/article',output:path.join(dir,'article'),executablePath:browser});assert.equal(r.acquired,'success');assert.equal(r.content,'needs_source_review');
  for(const name of ['empty','login']){r=await capture({url:base+'/'+name,output:path.join(dir,name),executablePath:browser});assert.equal(r.acquired,'success');assert.equal(r.content,'unusable');await assert.rejects(fs.access(path.join(dir,name,'body.md')));}
  await assert.rejects(capture({url:base+'/article',output:path.join(dir,'article'),executablePath:browser}));
  assert.equal(publicUrl('https://example.org/a?token=FAKE_TEST_TOKEN&id=2'),'https://example.org/a?id=2');
  assert.ok(Object.keys(process.env).length===Object.keys(during).length && Object.keys(during).every(k=>process.env[k]===during[k]),'environment changed');
  const config={providers:[{id:'one',adapter:'gemini',model:'teaching',key_env:'TEACHING_ONLY_KEY',endpoint:'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'},{id:'unselected',adapter:'chat-completions',model:'teaching',key_env:'UNSELECTED_KEY',endpoint:'https://example.org/api'}]};
  const file=path.join(dir,'config.json');await fs.writeFile(file,JSON.stringify(config));const image=path.join(dir,'teaching.png');await fs.writeFile(image,'offline test fixture');
  const data={one:{candidates:[{finishReason:'STOP',content:{parts:[{text:'模拟视觉转录'}]}}]}};
  r=await runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'vision'),configPath:file,routes:['one'],responses:data});assert.equal(r.one.status,'success');assert.equal(Object.keys(r).length,1);
  const resultFile=path.join(dir,'vision/routes/one.md');const old=await fs.stat(resultFile);
  r=await runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'vision'),configPath:file,routes:['one'],responses:{},resume:true});assert.equal(r.one.status,'success');assert.equal((await fs.stat(resultFile)).mtimeMs,old.mtimeMs);
  await fs.writeFile(image,'changed input');await assert.rejects(runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'vision'),configPath:file,routes:['one'],responses:data,resume:true}));
  r=await runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'bad-vision'),configPath:file,routes:['one'],responses:{}});assert.equal(r.one.status,'failed_or_unknown');
  r=await runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'bad-vision'),configPath:file,routes:['one'],responses:data,resume:true});assert.equal(r.one.status,'failed_or_unknown');
  r=await runVlmCrossCheck({imagePath:image,outDir:path.join(dir,'bad-vision'),configPath:file,routes:['one'],responses:data,resume:true,retryUnknown:true});assert.equal(r.one.status,'success');
  for(const data of [{}, {error:{message:'failure'}}, {candidates:[{finishReason:'MAX_TOKENS',content:{parts:[{text:'partial'}]}}]}, {candidates:[{finishReason:'STOP',content:{parts:[{text:''}]}}]}])assert.throws(()=>textFrom('gemini',data));
  assert.ok(Object.keys(process.env).length===Object.keys(during).length && Object.keys(during).every(k=>process.env[k]===during[k]),'environment changed');
  console.log(JSON.stringify({status:'passed',checks:['article','empty','login','no_overwrite','safe_url','selected_vision_route_only','incomplete_empty_error_responses','environment_unchanged','vision_valid_resume','vision_input_binding','vision_unknown_no_auto_retry'],directory:dir}));
} finally {await new Promise(resolve=>server.close(resolve));for(const k of Object.keys(process.env))if(!(k in originalEnv))delete process.env[k];Object.assign(process.env,originalEnv);}
