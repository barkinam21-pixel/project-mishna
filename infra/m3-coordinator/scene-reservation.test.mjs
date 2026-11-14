import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  createSceneReservationClass,validateOfflineAdmission,sha256
} from "./scene-reservation-core.mjs";

class Base {
  constructor(ctx,env){this.ctx=ctx;this.env=env;}
}
const Coordinator=createSceneReservationClass(Base);
function open(db) {
  db.exec("PRAGMA busy_timeout=1000");
  return {
    sql: {
      exec(q,...args) {
        const statement=db.prepare(q);
        return {toArray(){return statement.all(...args);}};
      }
    },
    transactionSync(callback) {
      db.exec("BEGIN IMMEDIATE");
      try { const result=callback();db.exec("COMMIT");return result; }
      catch(error){db.exec("ROLLBACK");throw error;}
    }
  };
}
function object(db) {
  const ctx={
    storage:open(db),
    blockConcurrencyWhile(fn) {this.initializing=Promise.resolve(fn());return this.initializing;}
  };
  return new Coordinator(ctx,{});
}
function admission() {
  return {
    status:"OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",
    live_dispatch_enabled:false,
    max_charge_usd:0,
    scene_id:"ACT1-PROLOGUE",
    request_id:"a".repeat(32),
    history_sha256:"b".repeat(64),
    historical_attempts:6,
    max_attempts:2,
    total_attempt_limit:8,
    shot_ids:["EP-P01","EP-P02"],
    asset_keys:{"EP-P01":"1".repeat(64),"EP-P02":"2".repeat(64)}
  };
}
async function receipt(a,shot) {
  return {
    kind:"OFFLINE_FAKE_NOT_IMAGE",
    sha256:await sha256("M3_FAKE_IMAGE_V1:"+a.scene_id+":"+shot+":"+a.asset_keys[shot]),
    accepted:false,provider_calls:0,external_cost_usd:0
  };
}
async function setup() {
  const dir=mkdtempSync(join(tmpdir(),"m3-coordinator-"));
  const path=join(dir,"ledger.sqlite");
  const db=new DatabaseSync(path);
  const do1=object(db);
  await do1.ctx.initializing;
  return {do1,db,path,cleanup(){db.close();rmSync(dir,{recursive:true,force:true});}};
}
test("real SQLite: immutable baseline, scoped tickets, replay without a second reservation",async t=>{
  const h=await setup();t.after(()=>h.cleanup());const a=admission();
  assert.deepEqual(await h.do1.beginOffline(a),{
    status:"OFFLINE_READY",replay:false,request_id:a.request_id,live_dispatch_enabled:false});
  const again=await h.do1.beginOffline(a);
  assert.equal(again.replay,true);
  await assert.rejects(h.do1.beginOffline({...a,request_id:"c".repeat(32)}),/SCENE_ALREADY_BOUND/);
  await assert.rejects(h.do1.beginOffline({...a,max_attempts:1,total_attempt_limit:7}),/SCENE_ALREADY_BOUND/);
  assert.equal((await h.do1.inspectOffline()).baseline_attempts,6);
  assert.equal((await h.do1.inspectOffline()).baseline_sha256,"b".repeat(64));
});
test("real SQLite: two synchronous competing reservations result in exactly one",async t=>{
  const h=await setup();t.after(()=>h.cleanup());const a=admission();
  await h.do1.beginOffline(a);
  const responses=await Promise.allSettled([
    h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"}),
    h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"})
  ]);
  assert.equal(responses.filter(r=>r.status==="fulfilled").length,1);
  assert.equal(responses.filter(r=>r.status==="rejected").length,1);
  const status=await h.do1.inspectOffline();
  assert.equal(status.attempts.length,1);
  assert.equal(status.attempts[0].outcome,"SUBMISSION_UNCERTAIN_NO_RETRY");
  assert.equal(status.external_inference_requests,0);
  assert.equal(status.live_dispatch_enabled,false);
});
test("crash and SQLite reopen retain ambiguous reservation; no retry or next shot",async t=>{
  const h=await setup();const a=admission();
  await h.do1.beginOffline(a);
  const once=await h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"});
  h.db.close();
  const db2=new DatabaseSync(h.path);
  const rebooted=object(db2);
  await rebooted.ctx.initializing;
  t.after(()=>{db2.close();rmSync(h.path.substring(0,h.path.lastIndexOf("/")),{recursive:true,force:true});});
  const resumed=await rebooted.inspectOffline();
  assert.equal(resumed.attempts[0].token,once.token);
  assert.equal(resumed.requires_review,true);
  await assert.rejects(rebooted.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"}),/SHOT_NOT_NEXT_OR_REPLAY/);
  await assert.rejects(rebooted.reserveOffline({request_id:a.request_id,shot_id:"EP-P02"}),/PREVIOUS_ATTEMPT_UNCERTAIN/);
});
test("only exact deterministic fake receipts clear uncertainty; then ordered second shot",async t=>{
  const h=await setup();t.after(()=>h.cleanup());const a=admission();
  await h.do1.beginOffline(a);
  await h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"});
  const good=await receipt(a,"EP-P01");
  for(const bad of [
    {...good,provider_calls:1},
    {...good,sha256:"e".repeat(64)},
    {...good,accepted:true},
    {...good,external_cost_usd:0.1},
    {...good,privateUrl:"https://example.org/file"}
  ]) {
    await assert.rejects(h.do1.recordFakeReceipt({request_id:a.request_id,shot_id:"EP-P01",receipt:bad}),/FAKE_RECEIPT_INVALID/);
  }
  assert.equal((await h.do1.inspectOffline()).requires_review,true);
  assert.equal((await h.do1.recordFakeReceipt({
    request_id:a.request_id,shot_id:"EP-P01",receipt:good})).status,"OFFLINE_PARTIAL");
  await assert.rejects(h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"}),/SHOT_NOT_NEXT_OR_REPLAY/);
  await h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P02"});
  assert.equal((await h.do1.recordFakeReceipt({
    request_id:a.request_id,shot_id:"EP-P02",receipt:await receipt(a,"EP-P02")
  })).status,"OFFLINE_COMPLETE");
  assert.equal((await h.do1.inspectOffline()).attempts.length,2);
  await assert.rejects(h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P02"}),/SHOT_NOT_NEXT_OR_REPLAY/);
});
test("real SQLite: two separate object instances sharing durable DB never double-submit",async t=>{
  const h=await setup();const secondDb=new DatabaseSync(h.path);
  const do2=object(secondDb);
  await do2.ctx.initializing;
  t.after(()=>{secondDb.close();h.cleanup();});
  const a=admission();
  await h.do1.beginOffline(a);
  const results=await Promise.allSettled([
    h.do1.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"}),
    do2.reserveOffline({request_id:a.request_id,shot_id:"EP-P01"})
  ]);
  assert.equal(results.filter(x=>x.status==="fulfilled").length,1);
  assert.equal((await do2.inspectOffline()).attempts.length,1);
});
test("malformed or paid approvals are impossible to admit",async()=>{
  const good=admission();
  for(const change of [
    {live_dispatch_enabled:true},{max_charge_usd:1},{max_charge_usd:"0"},
    {status:"APPROVED_FOR_GENERATION"},{historical_attempts:0},
    {total_attempt_limit:200},{max_attempts:3},
    {asset_keys:{"EP-P01":"f".repeat(64)}},
    {shot_ids:["EP-P01","EP-P01"]},
    {history_sha256:"not-a-sha"}
  ]) assert.throws(()=>validateOfflineAdmission({...good,...change}),/M3_DO_/);
});
test("runtime adapter is deliberately unexposed and no provider SDK dependency",async()=>{
  const {readFileSync}=await import("node:fs");
  const txt=readFileSync(new URL("./worker.mjs",import.meta.url),"utf8");
  assert.match(txt,/status:404/);
  assert.doesNotMatch(txt,/\binfer\(|\/ai\/run|MISHNAH_DRIVE_OAUTH_JSON|CLOUDFLARE_API_TOKEN/);
});
