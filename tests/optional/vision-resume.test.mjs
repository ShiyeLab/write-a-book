import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {runVlmCrossCheck} from '../../tools/web-capture/vlm-bridge.mjs';

const ids=['binding','report','regular'];
async function fixture(t){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'book-vision-resume-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const imagePath=path.join(dir,'teaching.png'),configPath=path.join(dir,'providers.json');
  await fs.writeFile(imagePath,'offline image fixture');
  await fs.writeFile(configPath,JSON.stringify({providers:ids.map(id=>({id,adapter:'gemini',model:'teaching',key_env:'TEACHING_UNUSED_KEY',endpoint:'https://example.org/{model}'}))}));
  return {dir,imagePath,configPath};
}
const answer=id=>({candidates:[{finishReason:'STOP',content:{parts:[{text:'teaching '+id}]}}]});
async function snapshot(dir){
  const result={};
  for(const name of await fs.readdir(dir))result[name]=await fs.readFile(path.join(dir,name),'utf8');
  return result;
}

test('reserved route IDs keep independent results and resume without reading another response',async t=>{
  const f=await fixture(t),outDir=path.join(f.dir,'results'),reads=[];
  const responses=Object.fromEntries(ids.map(id=>[id,answer(id)]));
  const tracked=new Proxy(responses,{get(target,id){reads.push(id);return target[id];}});
  const args={...f,outDir,routes:ids};
  let results=await runVlmCrossCheck({...args,responses:tracked});
  assert.deepEqual(reads,ids);
  const binding=await fs.readFile(path.join(outDir,'binding.json'),'utf8');
  const routeFiles=await snapshot(path.join(outDir,'routes'));
  const mtimes=await Promise.all(ids.map(id=>fs.stat(path.join(outDir,'routes',id+'.md')).then(s=>s.mtimeMs)));
  for(const id of ids){assert.equal(results[id].status,'success');assert.equal(results[id].file,'routes/'+id+'.md');}
  reads.length=0;
  results=await runVlmCrossCheck({...args,responses:new Proxy({},{get(){throw Error('cached result must not request another response');}}),resume:true});
  for(const id of ids)assert.equal(results[id].status,'success');
  assert.equal(await fs.readFile(path.join(outDir,'binding.json'),'utf8'),binding);
  assert.deepEqual(await snapshot(path.join(outDir,'routes')),routeFiles);
  assert.deepEqual(await Promise.all(ids.map(id=>fs.stat(path.join(outDir,'routes',id+'.md')).then(s=>s.mtimeMs))),mtimes);
  const report=JSON.parse(await fs.readFile(path.join(outDir,'report.json'),'utf8'));
  assert.equal(JSON.parse(binding).layout_version,2);
  for(const id of ids)assert.equal(report.results[id].status,'success');
});

test('legacy layouts are rejected before response access or file changes',async t=>{
  const f=await fixture(t);
  for(const id of ids){
    const outDir=path.join(f.dir,id);await fs.mkdir(outDir);
    await fs.writeFile(path.join(outDir,'binding.json'),JSON.stringify({algorithm:'vision-v1'}));
    await fs.writeFile(path.join(outDir,id+'.json'),JSON.stringify({status:'success',file:id+'.md'}));
    await fs.writeFile(path.join(outDir,id+'.md'),'saved text');
    const before=await snapshot(outDir);
    const responses=new Proxy({},{get(){throw Error('response must not be read');}});
    await assert.rejects(runVlmCrossCheck({...f,outDir,routes:[id],responses,resume:true}),/unsupported_output_layout_use_new_directory/);
    assert.deepEqual(await snapshot(outDir),before);
  }
});

test('CLI explains old layout and keeps its files',async t=>{
  const f=await fixture(t),outDir=path.join(f.dir,'old'),responsePath=path.join(f.dir,'responses.json');
  await fs.mkdir(outDir);await fs.writeFile(path.join(outDir,'binding.json'),'{}');await fs.writeFile(responsePath,'{}');
  const before=await snapshot(outDir);
  const script=fileURLToPath(new URL('../../tools/web-capture/vlm-bridge.mjs',import.meta.url));
  const r=spawnSync(process.execPath,[script,'--image',f.imagePath,'--output',outDir,'--config',f.configPath,'--routes','regular','--responses',responsePath,'--resume'],{encoding:'utf8'});
  assert.equal(r.status,1);assert.match(r.stderr,/请使用新输出目录/);assert.deepEqual(await snapshot(outDir),before);
});
