import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {authStorage,bridgeJobs} from './chatgpt-store.mjs';
import {registerHooks} from 'node:module';
// Only the platform base class is shimmed; OAuth's actual protocol/crypto runs.
registerHooks({resolve(specifier,context,next){
  if(specifier==='cloudflare:workers')return {url:'data:text/javascript,export class WorkerEntrypoint {}',shortCircuit:true};
  return next(specifier,context);
}});
const {chatgptRequest,ORIGIN}=await import('./chatgpt-mcp.mjs');

function harness(){
  const dir=mkdtempSync(join(tmpdir(),'m3-chatgpt-')), stores=new Map();
  function storage(name){
    if(stores.has(name))return stores.get(name);
    const db=new DatabaseSync(join(dir,name+'.sqlite'));
    const s={db,sql:{exec(q,...a){const st=db.prepare(q);const rows=st.columns().length?st.all(...a): (st.run(...a),[]);return {toArray:()=>rows};}},transactionSync(f){db.exec('BEGIN IMMEDIATE');try{const v=f();db.exec('COMMIT');return v;}catch(e){db.exec('ROLLBACK');throw e;}},async transaction(f){db.exec('BEGIN IMMEDIATE');try{const v=await f();db.exec('COMMIT');return v;}catch(e){db.exec('ROLLBACK');throw e;}},async setAlarm(t){db.exec('CREATE TABLE IF NOT EXISTS test_alarm(t INTEGER)');db.prepare('INSERT INTO test_alarm VALUES(?)').run(t);}};
    stores.set(name,s);return s;
  }
  const env={M3_GATEWAY_HMAC_KEY:'ab'.repeat(32),M3_SCENE_RESERVATION:{getByName(name){return {
    async chatgptAuth(op,p){const s=authStorage(storage(name));if(op==='get')return s.get(p.key);if(op==='put')return s.put(p.key,p.value,p.options);if(op==='delete')return s.delete(p.key);if(op==='list')return s.list(p);if(op==='approvePending')return s.approvePending(p.id);throw Error('denied');},
    async chatgptJob(op,id){const s=bridgeJobs(storage(name),env);return s[op](id);},
    async production(op){assert.equal(op,'status');return {status:'PRODUCTION_NOT_INITIALIZED',attempt:null};}
  };}}};
  return {env,storage,async fetch(path,options={}){return chatgptRequest(new Request(ORIGIN+path,options),env,{waitUntil(){},passThroughOnException(){}});},reopen(){for(const s of stores.values())s.db.close();stores.clear();},close(){this.reopen();rmSync(dir,{recursive:true,force:true});}};
}

async function connection(h){
  const response=await h.fetch('/oauth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_name:'ChatGPT test',redirect_uris:['https://chatgpt.com/connector_platform_oauth_redirect'],grant_types:['authorization_code','refresh_token'],response_types:['code'],token_endpoint_auth_method:'none'})});
  assert.equal(response.status,201,await response.clone().text());const client=await response.json();
  const verifier='v'.repeat(64),challenge=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))).toString('base64url');
  const query=new URLSearchParams({response_type:'code',client_id:client.client_id,redirect_uri:client.redirect_uris[0],scope:'mishnah:control',state:'test-state',code_challenge:challenge,code_challenge_method:'S256',resource:ORIGIN+'/mcp'});
  const a=await h.fetch('/authorize?'+query);assert.equal(a.status,200,await a.clone().text());
  // no-referrer makes browser form POST Origin null and blocks real consent.
  assert.equal(a.headers.get('Referrer-Policy'),'strict-origin');
  const html=await a.text(),id=/name="pending_id" value="([a-f0-9]+)"/.exec(html)[1],handle=/name="handle" value="([^"]+)"/.exec(html)[1];
  const cookies=a.headers.getSetCookie().map(s=>s.split(';')[0]).join('; ');
  return {client,verifier,id,handle,cookies};
}
async function approve(h,c){
  const raw=JSON.stringify({owner:'barkinam21-pixel',operation:'approve',pending_id:c.id});
  const stamp=new Date().toISOString(),key=await crypto.subtle.importKey('raw',Buffer.from(h.env.M3_GATEWAY_HMAC_KEY,'hex'),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const sig=Buffer.from(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode('POST\n/m3/v1/connection\n'+stamp+'\n'+raw))).toString('hex');
  const r=await h.fetch('/m3/v1/connection',{method:'POST',headers:{'X-M3-Timestamp':stamp,'X-M3-Signature':sig},body:raw});assert.equal(r.status,200);
}

test('OAuth metadata and unauthenticated MCP are real protocol responses; no journal disclosure',async()=>{
  const h=harness();try{
    const r=await h.fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});assert.equal(r.status,401);assert.match(r.headers.get('www-authenticate'),/oauth-protected-resource/);
    const m=await h.fetch('/.well-known/oauth-authorization-server');assert.equal(m.status,200);const metadata=await m.json();assert.equal(metadata.issuer,ORIGIN);assert.ok(metadata.code_challenge_methods_supported.includes('S256'));
  }finally{h.close();}
});

test('actual OAuth library: owner approval, browser consent, PKCE token, authenticated status and durable job',async()=>{
 const h=harness();try{
  const c=await connection(h);
  const form=new URLSearchParams({handle:c.handle,pending_id:c.id,decision:'approve'});
  let r=await h.fetch('/authorize',{method:'POST',headers:{Cookie:c.cookies},body:form});assert.equal(r.status,403);
  await approve(h,c);
  r=await h.fetch('/authorize',{method:'POST',headers:{Cookie:c.cookies},body:form});assert.equal(r.status,302,await r.clone().text());
  const callback=new URL(r.headers.get('Location'));assert.equal(callback.origin,'https://chatgpt.com');assert.equal(callback.searchParams.get('state'),'test-state');
  const t=await h.fetch('/oauth/token',{method:'POST',body:new URLSearchParams({grant_type:'authorization_code',client_id:c.client.client_id,code:callback.searchParams.get('code'),code_verifier:c.verifier,redirect_uri:c.client.redirect_uris[0],resource:ORIGIN+'/mcp'})});
  assert.equal(t.status,200,await t.clone().text());const token=(await t.json()).access_token;
  async function rpc(method,params){const v=await h.fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})});assert.equal(v.status,200,await v.clone().text());return (await v.json()).result;}
  assert.equal((await rpc('initialize',{})).serverInfo.name,'Mishnah Independent Studio');
  const s=await rpc('tools/call',{name:'mishnah_status',arguments:{}});assert.equal(s.structuredContent.dispatch_permitted_once,false);
  const id='12'.repeat(16);let j=await rpc('tools/call',{name:'mishnah_check_connection',arguments:{request_id:id}});assert.equal(j.structuredContent.status,'QUEUED');
  j=await rpc('tools/call',{name:'mishnah_check_connection',arguments:{request_id:id}});assert.equal(j.structuredContent.replay,true);
  h.reopen();await bridgeJobs(h.storage('M3-CHATGPT-CONNECTION-JOBS-V1'),h.env).alarm();
  j=await rpc('tools/call',{name:'mishnah_job_result',arguments:{request_id:id}});assert.equal(j.structuredContent.status,'COMPLETE');assert.equal(j.structuredContent.result.inference_requests,0);
  assert.equal((await rpc('tools/call',{name:'generate_image',arguments:{}})).isError,true);
 }finally{h.close();}
});

test('OAuth cannot approve without signed owner or reuse expired pending ID',async()=>{
 const h=harness();try{
  const r=await h.fetch('/m3/v1/connection',{method:'POST',body:JSON.stringify({operation:'approve',owner:'barkinam21-pixel',pending_id:'00'.repeat(16)})});assert.equal(r.status,401);
  assert.throws(()=>authStorage(h.storage('limits')).approvePending('00'.repeat(16)),/EXPIRED/);
  const jobs=bridgeJobs(h.storage('job-limits'),h.env);await assert.rejects(jobs.enqueue('../bad'),/INVALID/);
 }finally{h.close();}
});

test('foreign Origin and oversized streaming bodies fail before OAuth state or commands',async()=>{
 const h=harness();try{
  let r=await h.fetch('/mcp',{method:'POST',headers:{Origin:'https://untrusted.example'},body:'{}'});assert.equal(r.status,403);
  r=await h.fetch('/authorize',{method:'POST',headers:{Origin:'null'},body:''});assert.equal(r.status,403);
  r=await h.fetch('/mcp',{method:'POST',body:'x'.repeat(32769)});assert.equal(r.status,413);
  assert.equal(h.storage('M3-CHATGPT-AUTH-V1').sql.exec("SELECT name FROM sqlite_master WHERE name='chatgpt_oauth'").toArray().length,0);
 }finally{h.close();}
});
