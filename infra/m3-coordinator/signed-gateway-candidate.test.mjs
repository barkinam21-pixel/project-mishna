/** Real SQLite + owner-HMAC gateway candidate tests. No sockets or Cloudflare. */
import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { createSceneReservationClass } from "./scene-reservation-core.mjs";
import { signedOfflineGateway,createSignatureForTesting }
  from "./signed-gateway-candidate.mjs";

const SECRET="ab".repeat(32); // FAKE TEST SECRET. Never a production credential.
const PATH="https://example.invalid/m3/v1/offline";
const OWNER="barkinam21-pixel";
const NOW=Date.parse("2026-11-14T20:00:00Z");
const TIMESTAMP="2026-11-14T20:00:00Z";
class Base{constructor(ctx,env){this.ctx=ctx;this.env=env;}}
const DO=createSceneReservationClass(Base);
function a(){
 return {
  status:"OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",live_dispatch_enabled:false,
  max_charge_usd:0,scene_id:"ACT1-PROLOGUE",request_id:"a".repeat(32),
  history_sha256:"b".repeat(64),historical_attempts:6,max_attempts:1,
  total_attempt_limit:7,shot_ids:["EP-P01"],
  asset_keys:{"EP-P01":"c".repeat(64)}
 };
}
function harness(){
 const db=new DatabaseSync(":memory:");
 const ctx={
  storage:{
   sql:{exec(q,...v){const result=db.prepare(q).all(...v);return{toArray:()=>result};}},
   transactionSync(fn){db.exec("BEGIN IMMEDIATE");try{const v=fn();db.exec("COMMIT");return v;}
                      catch(e){db.exec("ROLLBACK");throw e;}}
  },
  blockConcurrencyWhile(fn){this.ready=Promise.resolve(fn());return this.ready;}
 };
 const stub=new DO(ctx,{});
 const env={
  M3_GATEWAY_HMAC_KEY:SECRET,
  M3_SCENE_RESERVATION:{
    getByName(id){assert.equal(id,"M3-LEGACY-SHARED-JOURNAL-V1");return stub;}
  }
 };
 return {stub,env,db,ready:ctx.ready};
}
async function invoke(env,operation,payload,options={}){
 const data={version:1,owner:OWNER,scene_id:"ACT1-PROLOGUE",
             operation,payload,...(options.envelope||{})};
 const raw=JSON.stringify(data);
 const stamp=options.timestamp||TIMESTAMP;
 const sig=await createSignatureForTesting(SECRET,stamp,raw);
 const request=new Request(options.url||PATH,{
  method:options.method||"POST",
  headers:{"x-m3-timestamp":stamp,
           "x-m3-signature":options.signature||sig},
  body:raw
 });
 const response=await signedOfflineGateway(request,env,{now:NOW});
 return {status:response.status,json:await response.json()};
}
test("no binding or secret or unknown route always fails closed",async()=>{
 const h=harness();await h.ready;
 for(const env of [{},{M3_GATEWAY_HMAC_KEY:SECRET},
                   {...h.env,M3_GATEWAY_HMAC_KEY:"invalid"}]){
  const x=await invoke(env,"status",{});
  assert.equal(x.status,503);
 }
 const x=await invoke(h.env,"status",{}, {url:"https://example.invalid/m3/v1/generate"});
 assert.equal(x.status,404);
 const m=await invoke(h.env,"status",{}, {method:"PUT"});
 assert.equal(m.status,404);
 h.db.close();
});
test("invalid owner, stale timestamp, wrong HMAC and live op are refused",async()=>{
 const h=harness();await h.ready;
 assert.equal((await invoke(h.env,"status",{}, {signature:"0".repeat(64)})).status,401);
 assert.equal((await invoke(h.env,"status",{}, {timestamp:"2026-11-14T18:00:00Z"})).status,401);
 assert.equal((await invoke(h.env,"status",{}, {envelope:{owner:"attacker"}})).status,403);
 assert.equal((await invoke(h.env,"generate",a())).status,400);
 assert.equal((await invoke(h.env,"begin",{...a(),scene_id:"ACT9-OTHER"})).status,403);
 const x=await invoke(h.env,"begin",{...a(),max_charge_usd:1});
 assert.equal(x.status,409);
 h.db.close();
});
test("HMAC gateway -> real SQLite DO reservation is atomic, persisted and never retried",async()=>{
 const h=harness();await h.ready;
 const admission=a();
 const first=await invoke(h.env,"begin",admission);
 assert.equal(first.status,200);
 assert.equal(first.json.status,"OFFLINE_READY");
 const requests=await Promise.all([
  invoke(h.env,"reserve",{request_id:admission.request_id,shot_id:"EP-P01"}),
  invoke(h.env,"reserve",{request_id:admission.request_id,shot_id:"EP-P01"})
 ]);
 assert.equal(requests.filter(x=>x.status===200).length,1);
 assert.equal(requests.filter(x=>x.status===409).length,1);
 const status=await invoke(h.env,"status",{});
 assert.equal(status.status,200);
 assert.equal(status.json.requires_review,true);
 assert.equal(status.json.attempts.length,1);
 assert.equal(status.json.baseline_attempts,6);
 assert.equal(status.json.external_inference_requests,0);
 assert.equal(status.json.live_dispatch_enabled,false);
 h.db.close();
});
test("two distinct scenes cannot reserve independently against one legacy journal",async()=>{
 const h=harness();await h.ready;
 const first=a();
 // Same six-attempt baseline; a different request/scene must NOT get its own DO.
 const second={...a(),scene_id:"ACT2-PROLOGUE",request_id:"d".repeat(32)};
 const attempts=await Promise.all([
  invoke(h.env,"begin",first),
  invoke(h.env,"begin",second,{envelope:{scene_id:second.scene_id}})
 ]);
 assert.deepEqual(attempts.map(x=>x.status).sort((x,y)=>x-y),[200,409]);
 const winner=attempts[0].status===200?first:second;
 const loser=attempts[0].status===200?second:first;
 const own=await invoke(h.env,"status",{}, {envelope:{scene_id:winner.scene_id}});
 assert.equal(own.status,200);
 assert.equal(own.json.scene_id,winner.scene_id);
 assert.equal(own.json.baseline_attempts,6);
 // A request bearing the winner's exact request_id cannot cross the scene
 // boundary by changing only the signed envelope scene_id.
 const cross=await invoke(h.env,"reserve",
  {request_id:winner.request_id,shot_id:"EP-P01"},
  {envelope:{scene_id:loser.scene_id}});
 assert.equal(cross.status,409);
 const leaked=await invoke(h.env,"status",{}, {envelope:{scene_id:loser.scene_id}});
 assert.equal(leaked.status,409);
 const valid=await invoke(h.env,"reserve",
  {request_id:winner.request_id,shot_id:"EP-P01"},
  {envelope:{scene_id:winner.scene_id}});
 assert.equal(valid.status,200);
 const state=await invoke(h.env,"status",{}, {envelope:{scene_id:winner.scene_id}});
 assert.equal(state.json.attempts.length,1);
 assert.equal(state.json.external_inference_requests,0);
 assert.equal(state.json.live_dispatch_enabled,false);
 h.db.close();
});
test("no billing or images API can appear in the gateway's implementation",async()=>{
 const {readFileSync}=await import("node:fs");
 const code=readFileSync(new URL("./signed-gateway-candidate.mjs",import.meta.url),"utf8");
 for(const token of ["workers/ai/run", "CloudflareClient", "MISHNAH_DRIVE_OAUTH_JSON",
                     "fetch('https://api.cloudflare.com", "CLOUDFLARE_API_TOKEN"]){
  assert.ok(!code.includes(token),token);
 }
 const defaultWorker=readFileSync(new URL("./worker.mjs",import.meta.url),"utf8");
 assert.match(defaultWorker,/status:404/); // Candidate is NOT deployed by default.
});

test('production route is separately signed, isolated, closed without protected config',async t=>{
 const h=harness();t.after(()=>h.db.close());await h.ready;
 const names=[];h.env.M3_SCENE_RESERVATION.getByName=id=>{names.push(id);return h.stub;};
 const body=JSON.stringify({version:1,owner:OWNER,scene_id:'ACT1-PROLOGUE',operation:'status',payload:{}});
 const {createHmac}=await import('node:crypto');
 const sig=createHmac('sha256',Buffer.from(SECRET,'hex')).update('POST\n/m3/v1/production\n'+TIMESTAMP+'\n'+body).digest('hex');
 const req=signature=>new Request('https://example.invalid/m3/v1/production',{method:'POST',body,headers:{'x-m3-timestamp':TIMESTAMP,'x-m3-signature':signature}});
 const good=await signedOfflineGateway(req(sig),h.env,{now:NOW});assert.equal(good.status,200);assert.equal((await good.json()).status,'PRODUCTION_NOT_INITIALIZED');
 assert.deepEqual(names,['M3-PRODUCTION-SHARED-JOURNAL-V1']);
 const wrongPath=await createSignatureForTesting(SECRET,TIMESTAMP,body);
 assert.equal((await signedOfflineGateway(req(wrongPath),h.env,{now:NOW})).status,401);
 const reserve=JSON.stringify({version:1,owner:OWNER,scene_id:'ACT1-PROLOGUE',operation:'reserve',payload:{}});
 const signature=createHmac('sha256',Buffer.from(SECRET,'hex')).update('POST\n/m3/v1/production\n'+TIMESTAMP+'\n'+reserve).digest('hex');
 assert.equal((await signedOfflineGateway(new Request('https://example.invalid/m3/v1/production',{method:'POST',body:reserve,headers:{'x-m3-timestamp':TIMESTAMP,'x-m3-signature':signature}}),h.env,{now:NOW})).status,409);
});
