// 网页正文采集：DOM/Readability、失败信号、单独启用的视觉转录。
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export function signals(text) {
  return [['login',/请登录|登录后|please log ?in|sign ?in to continue/i],['captcha',/验证码|人机验证|captcha|are you human/i],['paywall',/付费阅读|会员专享|subscribe to read/i],['forbidden',/访问被拒|access denied|forbidden/i]].filter(([,p])=>p.test(text.slice(0,8000))).map(([k])=>k);
}
export function publicUrl(value) {
  const u=new URL(value);
  if (!['http:','https:'].includes(u.protocol) || u.username || u.password) throw Error('invalid_url');
  for (const k of [...u.searchParams.keys()]) if (/key|token|auth|secret|signature|password|credential/i.test(k)) u.searchParams.delete(k);
  u.hash='';return u.href;
}
function proxyFor(url) {
  const host=new URL(url).hostname;
  const bypass=(process.env.no_proxy || process.env.NO_PROXY || '').split(',').map(x=>x.trim()).filter(Boolean);
  if (bypass.some(x=>x==='*'||host===x||host.endsWith(x.startsWith('.')?x:'.'+x))) return undefined;
  const proxy=new URL(url).protocol==='https:' ? (process.env.https_proxy||process.env.HTTPS_PROXY||process.env.http_proxy||process.env.HTTP_PROXY) : (process.env.http_proxy||process.env.HTTP_PROXY);
  if (!proxy) return undefined;
  const u=new URL(proxy);return {server:u.protocol+'//'+u.host,username:decodeURIComponent(u.username),password:decodeURIComponent(u.password)};
}
export async function capture({url,output,timeout=30000,minText=80,executablePath,screenshot=false,visionConfig,visionRoutes=[],executeVision=false}) {
  if(!(timeout>=1000&&timeout<=180000&&minText>=1))throw Error('invalid_limits');
  const safe=publicUrl(url);
  // 带鉴权查询参数的 URL 不发送也不存盘；使用者需提供可公开获取的页面。
  if (safe!==new URL(url).href.replace(/#.*$/,'')) throw Error('credential_or_noncanonical_query_not_supported');
  await fs.mkdir(output,{recursive:false});
  const metadata={url:safe,acquired:'failed',content:'unusable',failureKinds:[],visual:null,capturedAt:new Date().toISOString()};
  let browser;
  try {
    const [{chromium},{JSDOM},{Readability},{default:Turndown}]=await Promise.all([import('playwright'),import('jsdom'),import('@mozilla/readability'),import('turndown')]);
    browser=await chromium.launch({headless:true,executablePath,proxy:proxyFor(url)});
    const page=await browser.newPage();
    const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout});
    metadata.httpStatus=response?.status()??null;
    metadata.url=publicUrl(page.url());
    metadata.acquired=response && response.ok()?'success':'failed';
    const visible=await page.locator('body').innerText({timeout});
    metadata.failureKinds=signals(visible+' '+await page.title());
    let html='',text='';
    if (metadata.acquired==='success' && !metadata.failureKinds.length) {
      for (const selector of ['main','article','[role="main"]','.markdown-body','.content']) {
        const el=page.locator(selector).first();
        if (await el.count()) {
          const t=await el.innerText();
          if(t.replace(/\s/g,'').length>=minText){text=t;html=await el.evaluate(e=>e.outerHTML);metadata.strategy='dom:'+selector;break;}
        }
      }
      if(!text){const dom=new JSDOM(await page.content(),{url:page.url()});const parsed=new Readability(dom.window.document).parse();
        if(parsed?.textContent?.replace(/\s/g,'').length>=minText){text=parsed.textContent;html=parsed.content;metadata.strategy='readability';}}
    }
    if (text) {
      const td=new Turndown({headingStyle:'atx',codeBlockStyle:'fenced'});td.keep(['table','tr','td','th']);
      const md=td.turndown(html).replace(/\]\(([^)]+)\)/g,(m,target)=>{try{return ']('+publicUrl(new URL(target,metadata.url).href)+')';}catch{return m;}});
      await fs.writeFile(path.join(output,'body.md'),md+'\n',{flag:'wx'});metadata.content='needs_source_review';metadata.characters=text.length;
    }
    if(screenshot||executeVision)await page.screenshot({path:path.join(output,'page.png'),fullPage:true,timeout});
    // 视觉转录不自动晋升为正文；独立保存各路结果，保留分歧。
    if(executeVision){
      if(!visionConfig||!visionRoutes.length)throw Error('select_vision_routes');
      const {runVlmCrossCheck}=await import('./vlm-bridge.mjs');
      metadata.visual=await runVlmCrossCheck({imagePath:path.join(output,'page.png'),outDir:path.join(output,'vision'),configPath:visionConfig,routes:visionRoutes,execute:true,timeout});
    }
  } catch(e) {
    metadata.error=e.code==='ERR_MODULE_NOT_FOUND'?'missing_dependency_see_optional_tools':'capture_or_visual_failed';
  } finally {
    if(browser)await browser.close();
    const visualFailed=metadata.visual&&Object.values(metadata.visual).some(r=>r.status!=='success');
    metadata.status=metadata.content==='needs_source_review'?(metadata.error||visualFailed?'partial':'success'):'failed';
    await fs.writeFile(path.join(output,'metadata.json'),JSON.stringify(metadata,null,2)+'\n',{flag:'wx'});
  }
  return metadata;
}
async function main() {
  const args=process.argv.slice(2);
  if(args.includes('--help')){console.log('node capture.mjs URL --output NEW_DIR [--timeout MS] [--min-text N] [--browser PATH] [--screenshot] [--execute-vision --vision-config FILE --vision-routes a,b]');return;}
  const url=args.shift();const opts={url};
  const keys={'--output':'output','--timeout':'timeout','--min-text':'minText','--browser':'executablePath','--vision-config':'visionConfig'};
  while(args.length){const k=args.shift();if(k==='--screenshot')opts.screenshot=true;else if(k==='--execute-vision')opts.executeVision=true;else if(k==='--vision-routes')opts.visionRoutes=(args.shift()||'').split(',');else if(keys[k])opts[keys[k]]=args.shift();else throw Error('invalid_argument');}
  if(!opts.url||!opts.output)throw Error('url_and_output_required');
  opts.timeout=Number(opts.timeout||30000);opts.minText=Number(opts.minText||80);
  if(!(opts.timeout>=1000&&opts.timeout<=180000&&opts.minText>=1))throw Error('invalid_limits');
  const r=await capture(opts);console.log(JSON.stringify({status:r.status,acquired:r.acquired,content:r.content}));process.exitCode={success:0,partial:3,failed:1}[r.status];
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)main().catch(()=>{console.error('参数、依赖或新输出目录无效；见 docs/optional-tools.md');process.exitCode=1;});
