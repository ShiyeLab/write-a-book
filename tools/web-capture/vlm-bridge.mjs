// 各路线独立保存转录，续跑绑定截图和配置；不自动合并事实。
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const PROMPT='逐字转录截图可见文字，保留段落与表格。看不清标[待核]，不解释、不补写。';
const sha=value=>createHash('sha256').update(value).digest('hex');
const save=(file,data)=>fs.writeFile(file,JSON.stringify(data,null,2)+'\n');
export function textFrom(adapter,data){
  if(!data||data.error!=null)throw Error('service_error');
  let text;
  if(adapter==='gemini'){
    const c=data.candidates?.[0];if(c?.finishReason!=='STOP')throw Error('incomplete_response');
    text=c.content?.parts?.filter(p=>typeof p.text==='string'&&!p.thought).map(p=>p.text).join('\n');
  }else{const c=data.choices?.[0];if(c?.finish_reason!=='stop')throw Error('incomplete_response');text=c.message?.content;}
  if(typeof text!=='string'||!text.trim())throw Error('empty_response');return text;
}
export async function runVlmCrossCheck({imagePath,outDir,configPath,routes,execute=false,responses,timeout=60000,resume=false,retryUnknown=false}){
  if(!routes?.length||new Set(routes).size!==routes.length)throw Error('select_routes');
  if(!execute&&!responses)throw Error('explicit_execution_required');
  if(execute&&responses)throw Error('choose_offline_or_live');
  if(!(timeout>=1000&&timeout<=180000))throw Error('invalid_timeout');
  const config=JSON.parse(await fs.readFile(configPath,'utf8'));
  const selected=routes.map(id=>config.providers.find(p=>p.id===id));
  const fields=new Set(['id','adapter','model','key_env','endpoint']);
  if(selected.some(p=>!p||Object.keys(p).some(k=>!fields.has(k))||!/^[a-z0-9_-]+$/.test(p.id)||!['gemini','chat-completions'].includes(p.adapter)||!p.model||!(/^[A-Za-z_][A-Za-z0-9_]*$/).test(p.key_env)))throw Error('invalid_config');
  for(const p of selected){const u=new URL(p.endpoint);if(u.protocol!=='https:'||u.search||u.username||u.password)throw Error('invalid_endpoint');}
  const bytes=await fs.readFile(imagePath),image=bytes.toString('base64');
  const mode=execute?'live':'offline_fixture';
  const binding={image_sha256:sha(bytes),selected,mode,prompt:PROMPT,algorithm:'vision-v1',layout_version:2};
  const routesDir=path.join(outDir,'routes');
  try{await fs.mkdir(outDir,{recursive:false});await fs.mkdir(routesDir);await save(path.join(outDir,'binding.json'),binding);}
  catch(e){
    if(e.code!=='EEXIST'||!resume)throw e;
    let old,routeDirectory;
    try{old=JSON.parse(await fs.readFile(path.join(outDir,'binding.json'),'utf8'));routeDirectory=(await fs.stat(routesDir)).isDirectory();}catch{}
    if(old?.layout_version!==2||!routeDirectory)throw Error('unsupported_output_layout_use_new_directory');
    if(JSON.stringify(old)!==JSON.stringify(binding))throw Error('resume_input_or_config_changed');
  }
  const results=Object.fromEntries(routes.map(id=>[id,{status:'not_processed'}]));
  const progress=()=>save(path.join(outDir,'report.json'),{mode,results,merged:false});
  await progress();let fetch,dispatcher;
  if(execute){const undici=await import('undici');fetch=undici.fetch;dispatcher=new undici.EnvHttpProxyAgent();}
  try {
    for(const [i,p] of selected.entries()){
      console.log(`vision ${i+1}/${selected.length}: ${p.id}`);
      const file=path.join(routesDir,p.id+'.md'),record=path.join(routesDir,p.id+'.json');
      if(resume){
        let old;try{old=JSON.parse(await fs.readFile(record,'utf8'));}catch{}
        if(old?.status==='failed_or_unknown'&&!retryUnknown){results[p.id]=old;await progress();continue;}
        if(old?.status==='success'){
          let text;try{text=await fs.readFile(file,'utf8');}catch{}
          if(text?.trim()&&sha(text)===old.text_sha256){results[p.id]=old;await progress();continue;}
        }
      }
      const key=execute?(process.env[p.key_env]||''):'';
      if(execute&&!key)results[p.id]={status:'missing_key',variable:p.key_env,presence:'ABSENT'};
      else try{
        let data=responses?.[p.id];
        if(execute){
          const gemini=p.adapter==='gemini';
          const body=gemini?{contents:[{parts:[{inline_data:{mime_type:'image/png',data:image}},{text:PROMPT}]}]}:{model:p.model,messages:[{role:'user',content:[{type:'image_url',image_url:{url:'data:image/png;base64,'+image}},{type:'text',text:PROMPT}]}]};
          const headers={'Content-Type':'application/json'};headers[gemini?'x-goog-api-key':'Authorization']=gemini?key:'Bearer '+key;
          const r=await fetch(p.endpoint.replace('{model}',encodeURIComponent(p.model)),{method:'POST',headers,body:JSON.stringify(body),dispatcher,signal:AbortSignal.timeout(timeout)});
          if(!r.ok)throw Error('http_failure');data=await r.json();
        }
        let text=textFrom(p.adapter,data);if(key)text=text.split(key).join('[REDACTED]');text+='\n';
        await fs.writeFile(file,text);results[p.id]={status:'success',file:'routes/'+p.id+'.md',text_sha256:sha(text),quality:'not_reviewed'};
      }catch{results[p.id]={status:'failed_or_unknown',action:'检查服务端状态或输入；不自动重复提交'};}
      await save(record,results[p.id]);await progress();
    }
  }finally{if(dispatcher)await dispatcher.close();}
  return results;
}
async function main(){
  const args=process.argv.slice(2);if(args.includes('--help')){console.log('node vlm-bridge.mjs --image FILE --output NEW_DIR --config FILE --routes a,b [--execute | --responses JSON] [--timeout MS] [--resume] [--retry-unknown]');return;}
  const opts={};while(args.length){const k=args.shift();if(k==='--execute')opts.execute=true;else if(k==='--resume')opts.resume=true;else if(k==='--retry-unknown')opts.retryUnknown=true;else{const map={'--image':'imagePath','--output':'outDir','--config':'configPath','--routes':'routes','--responses':'responses','--timeout':'timeout'};if(!map[k])throw Error('invalid_argument');opts[map[k]]=args.shift();}}
  opts.routes=(opts.routes||'').split(',').filter(Boolean);if(opts.timeout)opts.timeout=Number(opts.timeout);if(opts.responses)opts.responses=JSON.parse(await fs.readFile(opts.responses,'utf8'));
  const r=await runVlmCrossCheck(opts);const successes=Object.values(r).filter(x=>x.status==='success').length;process.exitCode=successes===opts.routes.length?0:successes?3:1;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)main().catch(e=>{console.error(e.message==='unsupported_output_layout_use_new_directory'?'输出目录为旧版或不完整布局，请使用新输出目录；原结果已保留。':'配置、依赖、输出目录或续跑绑定无效；见 docs/optional-tools.md');process.exitCode=1;});
