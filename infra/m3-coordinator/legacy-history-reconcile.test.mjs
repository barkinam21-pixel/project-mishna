/** Adversarial six-attempt migration tests on actual SQLite; NO network. */
import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync,rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createSceneReservationClass,sha256 }
  from "./scene-reservation-core.mjs";
import { createOfflineLegacyReconciler,legacyCanonicalJSON }
  from "./legacy-history-reconcile.mjs";

class Base{constructor(ctx,env){this.ctx=ctx;this.env=env;}}
const DO=createSceneReservationClass(Base);
function store(db){
  return {
    sql:{exec(q,...v){const out=db.prepare(q).all(...v);return{toArray:()=>out};}},
    transactionSync(fn){
      db.exec("BEGIN IMMEDIATE");
      try{const v=fn();db.exec("COMMIT");return v;}
      catch(e){db.exec("ROLLBACK");throw e;}
    }
  };
}
function actor(db){
  const storage=store(db);
  const ctx={storage,blockConcurrencyWhile(fn){
    this.ready=Promise.resolve(fn());return this.ready;
  }};
  const core=new DO(ctx,{});
  return {core,ctx,storage,migration:createOfflineLegacyReconciler(storage)};
}
function fixture(){
  return {
    attempts:Array.from({length:6},(_,i)=>({
      request_id:(i+1).toString(16).repeat(32),sequence:i+1,
      stage:i<4?"OLD":"CANDIDATE",provider_requests:i>=4?1:0
    })),
    candidates:[
      {shot_id:"OPN02",accepted:false,sha256:"2".repeat(64)},
      {shot_id:"OPN03",accepted:false,sha256:"3".repeat(64)}
    ],
    note:"\u05de\u05e9\u05e0\u05d4"
  };
}
async function admission(history){
  return {status:"OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",
    live_dispatch_enabled:false,max_charge_usd:0,
    scene_id:"ACT1-PROLOGUE",request_id:"a".repeat(32),
    history_sha256:await sha256(legacyCanonicalJSON(history)),
    historical_attempts:6,max_attempts:1,total_attempt_limit:7,
    shot_ids:["OPN02"],asset_keys:{OPN02:"f".repeat(64)}
  };
}
async function setup(){
  const dir=mkdtempSync(join(tmpdir(),"m3-legacy-offline-"));
  const path=join(dir,"shared.sqlite");
  const db=new DatabaseSync(path);const a=actor(db);await a.ctx.ready;
  const history=fixture(),spec=await admission(history);
  await a.core.beginOffline(spec);
  return {dir,path,db,a,history,spec,close(){
    db.close();rmSync(dir,{recursive:true,force:true});
  }};
}
function params(h,readPrivateHistory=async()=>structuredClone(h.history)){
  return {admission:h.spec,readPrivateHistory};
}

test("six synthetic attempts and BOTH unapproved candidates preserved exactly; replay is read-only",async t=>{
  const h=await setup();t.after(()=>h.close());
  const first=await h.a.migration.bootstrapOffline(params(h));
  assert.equal(first.status,"OFFLINE_PREFIX_IMPORTED_NO_LIVE_PROOF");
  assert.equal(first.replay,false);
  const row=h.db.prepare("SELECT * FROM legacy_history_bootstrap").get();
  assert.equal(row.baseline_sha256,h.spec.history_sha256);
  assert.equal(row.attempts,6);
  assert.deepEqual(JSON.parse(row.canonical_json),h.history);
  assert.deepEqual(JSON.parse(row.canonical_json).candidates.map(x=>x.accepted),[false,false]);
  assert.equal(h.db.prepare("SELECT COUNT(*) AS n FROM legacy_history_attempts").get().n,6);
  assert.equal((await h.a.migration.bootstrapOffline(params(h))).replay,true);
  const check=await h.a.migration.reconcileOffline(params(h));
  assert.equal(check.status,"OFFLINE_PREFIX_MATCH_NO_REMOTE_CAS");
  assert.equal(check.provider_submission_authorized,false);
  assert.equal(check.live_dispatch_enabled,false);
  assert.equal(check.offline_reservations,0);
});
test("caller hash alone or missing independent private read NEVER bootstraps",async t=>{
  const h=await setup();t.after(()=>h.close());
  await assert.rejects(h.a.migration.bootstrapOffline({admission:h.spec}),
    /INDEPENDENT_PRIVATE_READER_REQUIRED/);
  const forged=structuredClone(h.history);forged.attempts[2].sequence=99;
  await assert.rejects(h.a.migration.bootstrapOffline(params(h,async()=>forged)),
    /STALE_OR_FORGED_BASELINE/);
  const fake={...h.spec,history_sha256:"c".repeat(64)};
  await assert.rejects(h.a.migration.bootstrapOffline({...params(h),admission:fake}),
    /STALE_OR_FORGED_BASELINE/);
  assert.equal(h.db.prepare("SELECT COUNT(*) AS n FROM legacy_history_bootstrap").get().n,0);
});
test("changed content with the SAME attempt count, or modified candidates, fails reconciliation",async t=>{
  const h=await setup();t.after(()=>h.close());
  await h.a.migration.bootstrapOffline(params(h));
  const edited=structuredClone(h.history);edited.attempts[5].stage="APPROVED";
  await assert.rejects(h.a.migration.reconcileOffline(params(h,async()=>edited)),
    /STALE_OR_FORGED_BASELINE/);
  const alteredCandidate=structuredClone(h.history);
  alteredCandidate.candidates[0].accepted=true;
  await assert.rejects(h.a.migration.reconcileOffline(params(h,async()=>alteredCandidate)),
    /STALE_OR_FORGED_BASELINE/);
  const append=structuredClone(h.history);
  append.attempts.push({request_id:"d".repeat(32)});
  await assert.rejects(h.a.migration.reconcileOffline(params(h,async()=>append)),
    /SIX_ATTEMPT_HISTORY_INVALID/);
  assert.equal((await h.a.migration.reconcileOffline(params(h))).historical_attempts,6);
});
test("two connections cannot overwrite imported history; stale writer is rejected",async t=>{
  const h=await setup();const second=new DatabaseSync(h.path);
  const b=actor(second);await b.ctx.ready;
  t.after(()=>{second.close();h.close();});
  const result=await Promise.allSettled([
    h.a.migration.bootstrapOffline(params(h)),
    b.migration.bootstrapOffline(params(h))
  ]);
  assert.equal(result.filter(x=>x.status==="fulfilled").length,2);
  assert.equal(result.filter(x=>x.value?.replay===false).length,1);
  assert.equal(result.filter(x=>x.value?.replay===true).length,1);
  const changed=structuredClone(h.history);changed.attempts[0].sequence=42;
  const staleSpec=await admission(changed);
  await assert.rejects(b.migration.bootstrapOffline({
    admission:staleSpec,readPrivateHistory:async()=>changed
  }),/COORDINATOR_SCOPE_MISMATCH/);
  assert.equal(h.db.prepare("SELECT COUNT(*) AS n FROM legacy_history_bootstrap").get().n,1);
});
test("crash before COMMIT rolls back every historical row; restart imports only once",async t=>{
  const h=await setup();
  await assert.rejects(h.a.migration.bootstrapOffline({
    ...params(h),failAfterInsert:true
  }),/SIMULATED_CRASH_BEFORE_COMMIT/);
  assert.equal(h.db.prepare("SELECT COUNT(*) AS n FROM legacy_history_bootstrap").get().n,0);
  assert.equal(h.db.prepare("SELECT COUNT(*) AS n FROM legacy_history_attempts").get().n,0);
  h.db.close();
  const reopened=new DatabaseSync(h.path);const b=actor(reopened);await b.ctx.ready;
  t.after(()=>{reopened.close();rmSync(h.dir,{recursive:true,force:true});});
  assert.equal((await b.migration.bootstrapOffline(params(h))).replay,false);
  assert.equal((await b.migration.bootstrapOffline(params(h))).replay,true);
  assert.equal(reopened.prepare("SELECT COUNT(*) AS n FROM legacy_history_attempts").get().n,6);
});
test("tampered stored attempt cannot be overwritten or reconciled silently",async t=>{
  const h=await setup();t.after(()=>h.close());
  await h.a.migration.bootstrapOffline(params(h));
  h.db.prepare("UPDATE legacy_history_attempts SET canonical_json='{}' WHERE ordinal=3").run();
  await assert.rejects(h.a.migration.bootstrapOffline(params(h)),
    /MIGRATED_PREFIX_CORRUPTED/);
  await assert.rejects(h.a.migration.reconcileOffline(params(h)),
    /MIGRATED_PREFIX_CORRUPTED/);
});
test("uncertain reservation stays no-retry after restart; migration after reservation rejected",async t=>{
  const h=await setup();
  await h.a.migration.bootstrapOffline(params(h));
  const once=await h.a.core.reserveOffline({request_id:h.spec.request_id,shot_id:"OPN02"});
  assert.equal(once.status,"OFFLINE_RESERVED_UNCERTAIN_NO_RETRY");
  const check=await h.a.migration.reconcileOffline(params(h));
  assert.equal(check.requires_review,true);
  assert.equal(check.provider_submission_authorized,false);
  await assert.rejects(h.a.migration.bootstrapOffline(params(h)),
    /RESERVATION_ALREADY_STARTED_NO_MIGRATION/);
  h.db.close();
  const reopened=new DatabaseSync(h.path);const b=actor(reopened);await b.ctx.ready;
  t.after(()=>{reopened.close();rmSync(h.dir,{recursive:true,force:true});});
  assert.equal((await b.core.inspectOffline()).requires_review,true);
  await assert.rejects(b.core.reserveOffline({request_id:h.spec.request_id,shot_id:"OPN02"}),
    /SHOT_NOT_NEXT_OR_REPLAY/);
  assert.equal((await b.migration.reconcileOffline(params(h))).requires_review,true);
});
test("migration is offline-only and not a public gateway operation",async()=>{
  const {readFileSync}=await import("node:fs");
  const gateway=readFileSync(new URL("./signed-gateway-candidate.mjs",import.meta.url),"utf8");
  const worker=readFileSync(new URL("./worker.mjs",import.meta.url),"utf8");
  assert.doesNotMatch(gateway,/bootstrapOffline|reconcileOffline|legacy-history-reconcile/);
  assert.match(worker,/status:404/);
  assert.equal(legacyCanonicalJSON({z:"\u05d0",a:1}),'{"a":1,"z":"\\u05d0"}');
});
