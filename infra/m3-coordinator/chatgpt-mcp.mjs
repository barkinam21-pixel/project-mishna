/** OAuth-protected ChatGPT interface to EXISTING M3. No image inference here. */
import OAuthProvider from '@cloudflare/workers-oauth-provider';
import {DurableOAuthKV} from './chatgpt-store.mjs';

export const ORIGIN='https://mishnah-m3-coordinator-staging.barkinam21.workers.dev';
const SCOPE='mishnah:control';
const OWNER='barkinam21-pixel';
const encoder=new TextEncoder();
const reply=(v,status=200,headers={})=>Response.json(v,{status,headers:{'Cache-Control':'no-store',...headers}});
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const digest=async v=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(v))),b=>b.toString(16).padStart(2,'0')).join('');

async function boundedRequest(request,limit){
  if(Number(request.headers.get('content-length')||0)>limit)throw Error('REQUEST_TOO_LARGE');
  const reader=request.body?.getReader(),parts=[];let size=0;
  if(reader)while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>limit){await reader.cancel();throw Error('REQUEST_TOO_LARGE');}parts.push(value);}
  const raw=new Uint8Array(size);let offset=0;for(const part of parts){raw.set(part,offset);offset+=part.byteLength;}
  return new Request(request.url,{method:request.method,headers:request.headers,body:raw,redirect:'manual'});
}

const tools=[
  {name:'mishnah_status',description:'Read the actual private Mishnah M3 production status. Use this for מסע אל המשנה. This never generates an image or grants image authorization.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}},
  {name:'mishnah_check_connection',description:'Queue one persistent zero-inference cloud connection check for Mishnah M3. It continues after chat closes. Reuse request_id on duplicate requests. NOT image generation.',inputSchema:{type:'object',properties:{request_id:{type:'string',pattern:'^[a-f0-9]{32}$',description:'Unique 32-lowercase-hex idempotency key; reuse it when checking the same job.'}},required:['request_id'],additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,idempotentHint:true,openWorldHint:false}},
  {name:'mishnah_job_result',description:'Read the persistent result of a previously queued Mishnah connection-check job. Never resubmit a model request to obtain a missing result.',inputSchema:{type:'object',properties:{request_id:{type:'string',pattern:'^[a-f0-9]{32}$'}},required:['request_id'],additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}}
];

async function mcp(request,env,ctx) {
  if(ctx.props?.userId!==OWNER || !ctx.auth?.scope?.includes(SCOPE)) return reply({error:'OWNER_REQUIRED'},403);
  if(request.method==='GET') return new Response(null,{status:405,headers:{Allow:'POST'}});
  if(request.method!=='POST')return new Response(null,{status:405});
  const bytes=await request.arrayBuffer();if(bytes.byteLength>32768)return reply({error:'REQUEST_TOO_LARGE'},413);
  let v;try{v=JSON.parse(new TextDecoder().decode(bytes));}catch{return reply({error:'INVALID_JSON'},400);}
  if(v.jsonrpc!=='2.0'||Array.isArray(v))return reply({error:'INVALID_JSON_RPC'},400);
  if(v.id===undefined)return new Response(null,{status:202});
  let result;
  if(v.method==='initialize')result={protocolVersion:'2025-03-26',serverInfo:{name:'Mishnah Independent Studio',version:'1.0.0'},capabilities:{tools:{}},instructions:'Use M3 for Mishnah production; never substitute image_gen or GPT Image. Current tools provide real private status and durable no-inference checks only. Image generation remains CLOSED until the private executor, exact one-use authorization, rights, privacy and quota are verified. A connection check is never an image.'};
  else if(v.method==='ping')result={};
  else if(v.method==='tools/list')result={tools};
  else if(v.method==='tools/call'){
    try {
      const name=v.params?.name,args=v.params?.arguments||{};
      if(!args||typeof args!=='object'||Array.isArray(args))throw Error('INVALID_ARGUMENTS');
      let out;
      if(name==='mishnah_status'&&Object.keys(args).length===0){
        const s=await env.M3_SCENE_RESERVATION.getByName('M3-PRODUCTION-SHARED-JOURNAL-V1').production('status',{});
        out={m3_status:s.status,attempt_present:!!s.attempt,dispatch_permitted_once:false,permanent_image_executor_ready:false,inference_requests:0};
      }else if(['mishnah_check_connection','mishnah_job_result'].includes(name)&&Object.keys(args).join(',')==='request_id'){
        out=await env.M3_SCENE_RESERVATION.getByName('M3-CHATGPT-CONNECTION-JOBS-V1').chatgptJob(name==='mishnah_check_connection'?'enqueue':'get',args.request_id);
      }else throw Error('TOOL_OR_ARGUMENTS_NOT_ALLOWED');
      result={content:[{type:'text',text:JSON.stringify(out)}],structuredContent:out,isError:false};
    }catch{result={content:[{type:'text',text:'M3_COMMAND_BLOCKED_NO_INFERENCE'}],isError:true};}
  }else return reply({jsonrpc:'2.0',id:v.id,error:{code:-32601,message:'Method not found'}});
  return reply({jsonrpc:'2.0',id:v.id,result});
}

async function authorize(request,env) {
  const api=env.OAUTH_PROVIDER,kv=env.OAUTH_KV;
  if(request.method==='GET'){
    const a=await api.parseAuthRequest(request);
    const u=new URL(a.redirectUri);
    if(u.origin!=='https://chatgpt.com'||!(u.pathname==='/connector_platform_oauth_redirect'||/^\/connector\/oauth\/[A-Za-z0-9_-]+$/.test(u.pathname)))return reply({error:'CHATGPT_CALLBACK_REQUIRED'},403);
    if(a.scope.some(s=>s!==SCOPE&&s!=='offline_access'))return reply({error:'SCOPE_NOT_ALLOWED'},403);
    const consent=await api.beginConsent(a),id=crypto.randomUUID().replaceAll('-','');
    await kv.put('pending:'+id,JSON.stringify({handleHash:await digest(consent.handle),ownerApproved:false}),{expirationTtl:600});
    const headers=consent.headers;headers.set('Content-Type','text/html;charset=utf-8');headers.set('Referrer-Policy','no-referrer');headers.set('Cache-Control','no-store');
    const body=`<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><title>חיבור מסע אל המשנה</title><main><h1>חיבור ChatGPT למסע אל המשנה</h1><p>קריאת סטטוס פרטי והפעלת בדיקת חיבור ללא יצירת תמונות. אין הרשאת יצירה או חיוב.</p><p>החיבור ממתין לאישור בעל המערכת בערוץ M3 החתום.</p><p>מזהה חיבור: <code>${id}</code></p><form method="post" action="/authorize"><input type="hidden" name="handle" value="${escape(consent.handle)}"><input type="hidden" name="pending_id" value="${id}"><button name="decision" value="approve">אישור חיבור</button><button name="decision" value="deny">ביטול</button></form></main></html>`;
    return new Response(body,{headers});
  }
  if(request.method!=='POST')return reply({error:'METHOD_NOT_ALLOWED'},405);
  if(Number(request.headers.get('content-length')||0)>16384)return reply({error:'REQUEST_TOO_LARGE'},413);
  const f=await request.formData(),handle=String(f.get('handle')||''),id=String(f.get('pending_id')||'');
  if(f.get('decision')!=='approve'){
    const denied=await api.denyConsent(request,handle);return new Response(null,{status:302,headers:denied.headers});
  }
  if(!/^[a-f0-9]{32}$/.test(id))return reply({error:'PENDING_ID_INVALID'},403);
  const pending=await kv.get('pending:'+id,{type:'json'});
  if(!pending?.ownerApproved||pending.handleHash!==await digest(handle))return reply({error:'OWNER_SIGNED_APPROVAL_REQUIRED'},403);
  const approved=await api.approveConsent(request,handle,{scope:[SCOPE]});
  await kv.delete('pending:'+id);
  const done=await api.completeAuthorization({request:approved.request,userId:OWNER,metadata:{},scope:[SCOPE],props:{userId:OWNER}});
  approved.headers.set('Location',done.redirectTo);return new Response(null,{status:302,headers:approved.headers});
}

async function signedConnection(request,env) {
  if(request.method!=='POST')return reply({error:'NOT_FOUND'},404);
  const raw=await request.text();if(encoder.encode(raw).length>16384)return reply({error:'TOO_LARGE'},413);
  const stamp=request.headers.get('X-M3-Timestamp'),sig=request.headers.get('X-M3-Signature');
  if(!stamp||!Number.isFinite(Date.parse(stamp))||Math.abs(Date.now()-Date.parse(stamp))>60000||!/^[a-f0-9]{64}$/.test(sig||'')||!/^[a-f0-9]{64}$/.test(env.M3_GATEWAY_HMAC_KEY||''))return reply({error:'UNAUTHORIZED'},401);
  const hex=v=>Uint8Array.from(v.match(/../g),b=>parseInt(b,16));
  const key=await crypto.subtle.importKey('raw',hex(env.M3_GATEWAY_HMAC_KEY),{name:'HMAC',hash:'SHA-256'},false,['verify']);
  if(!await crypto.subtle.verify('HMAC',key,hex(sig),encoder.encode('POST\n/m3/v1/connection\n'+stamp+'\n'+raw)))return reply({error:'UNAUTHORIZED'},401);
  const v=JSON.parse(raw);
  if(v.owner!==OWNER)return reply({error:'SCOPE_INVALID'},403);
  if(v.operation==='approve'&&Object.keys(v).sort().join(',')==='operation,owner,pending_id'&&/^[a-f0-9]{32}$/.test(v.pending_id||''))
    return reply(await env.M3_SCENE_RESERVATION.getByName('M3-CHATGPT-AUTH-V1').chatgptAuth('approvePending',{id:v.pending_id}));
  if(['check','result'].includes(v.operation)&&Object.keys(v).sort().join(',')==='operation,owner,request_id'&&/^[a-f0-9]{32}$/.test(v.request_id||''))
    return reply(await env.M3_SCENE_RESERVATION.getByName('M3-CHATGPT-CONNECTION-JOBS-V1').chatgptJob(v.operation==='check'?'enqueue':'get',v.request_id));
  return reply({error:'SCOPE_INVALID'},403);
}

export async function chatgptRequest(request,env,ctx) {
  const path=new URL(request.url).pathname;
  if(!['/mcp','/authorize','/oauth/token','/oauth/register','/m3/v1/connection'].includes(path)&&!path.startsWith('/.well-known/'))return null;
  const origin=request.headers.get('Origin');
  if(origin&&origin!==ORIGIN&&origin!=='https://chatgpt.com')return reply({error:'ORIGIN_DENIED'},403);
  if(request.method==='POST'){
    try{request=await boundedRequest(request,path==='/mcp'?32768:16384);}catch{return reply({error:'REQUEST_TOO_LARGE'},413);}
  }
  if(path==='/m3/v1/connection'){
    try{return await signedConnection(request,env);}catch{return reply({error:'CONNECTION_APPROVAL_BLOCKED'},409);}
  }
  const bound={...env,OAUTH_KV:new DurableOAuthKV(env.M3_SCENE_RESERVATION)};
  const provider=new OAuthProvider({apiRoute:'/mcp',apiHandler:{fetch:mcp},defaultHandler:{fetch:async(req,e)=>{
    try{return new URL(req.url).pathname==='/authorize'?await authorize(req,e):reply({error:'NOT_FOUND'},404);}catch{return reply({error:'AUTHORIZATION_REJECTED'},400);}
  }},authorizeEndpoint:'/authorize',tokenEndpoint:'/oauth/token',clientRegistrationEndpoint:'/oauth/register',issuer:ORIGIN,resourceMetadata:{resource:ORIGIN+'/mcp',authorization_servers:[ORIGIN]},scopesSupported:[SCOPE],requiredScopes:[SCOPE],accessTokenTTL:3600,refreshTokenTTL:2592000});
  return provider.fetch(request,bound,ctx);
}
