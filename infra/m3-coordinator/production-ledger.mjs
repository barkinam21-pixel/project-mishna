/** Production methods for the EXISTING coordinator. No fetch/model calls.
 * Protected deployment configuration, never HTTP payload flags, opens gates.
 * Staging tables/singleton remain untouched. Shared production budget is global.
 */
import {sha256} from './scene-reservation-core.mjs';
const HASH=/^[a-f0-9]{64}$/;
const MODEL='@cf/black-forest-labs/flux-2-klein-4b';
const fail=code=>{throw Error('M3_PRODUCTION_'+code);};
const one=(s,q,...a)=>s.sql.exec(q,...a).toArray()[0];
export function productionMethods(storage, env){
 for(const ddl of [
  `CREATE TABLE IF NOT EXISTS production_baseline(singleton INTEGER PRIMARY KEY CHECK(singleton=1),hash TEXT NOT NULL,raw TEXT NOT NULL,config_hash TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS production_attempt(singleton INTEGER PRIMARY KEY CHECK(singleton=1),request_id TEXT UNIQUE NOT NULL,token TEXT UNIQUE NOT NULL,spec TEXT NOT NULL,phase TEXT NOT NULL,receipt TEXT,delivery TEXT)`
 ])storage.sql.exec(ddl);
 function config(){
  let c;try{c=JSON.parse(env.M3_PRODUCTION_CONFIG);}catch{fail('CONFIG_CLOSED');}
  if(!c || c.version!==1 || c.model!==MODEL || c.scene_id!=='ACT1-PROLOGUE' || c.shot_id!=='EP-P07' ||
     !/^[a-f0-9]{32}$/.test(c.request_id||'') || c.max_attempts!==1 || c.total_attempt_limit!==7 ||
     c.max_charge_usd!==0 || c.baseline_attempts!==6 ||
     ['history_sha256','body_sha256','draft_sha256','references_sha256'].some(k=>!HASH.test(c[k]||'')) ||
     ['owner_approved','synthesis_rights_verified','privacy_verified','free_hard_stop_verified','quota_verified','legacy_writers_fenced','private_storage_verified'].some(k=>c[k]!==true) ||
     !Number.isFinite(Date.parse(c.expires_at)) || Date.parse(c.expires_at)<=Date.now() || Date.parse(c.expires_at)>Date.now()+300000)fail('GATES_CLOSED');
  return c;
 }
 async function scope(){const c=config();return {c,hash:await sha256(JSON.stringify(c))};}
 function base(hash){const b=one(storage,'SELECT * FROM production_baseline');if(!b||b.config_hash!==hash)fail('BASELINE_OR_CONFIG_CHANGED');return b;}
 function current(token){const a=one(storage,'SELECT * FROM production_attempt');if(!a||a.token!==token)fail('RESERVATION_MISMATCH');return a;}
 return {
  async bootstrap({history_json}){
   const {c,hash}=await scope();
   if(typeof history_json!=='string'||history_json.length>2000000||await sha256(history_json)!==c.history_sha256)fail('HISTORY_HASH_MISMATCH');
   let h;try{h=JSON.parse(history_json);}catch{fail('HISTORY_INVALID');}
   if(!h||!Array.isArray(h.attempts)||h.attempts.length!==6||h.attempts.some(a=>!a||typeof a!=='object'||Array.isArray(a))||h.attempts.some(a=>a.request_id===c.request_id))fail('HISTORY_INVALID');
   return storage.transactionSync(()=>{
    const old=one(storage,'SELECT * FROM production_baseline');
    if(old&&(old.hash!==c.history_sha256||old.raw!==history_json||old.config_hash!==hash))fail('BASELINE_IMMUTABLE');
    if(!old)storage.sql.exec('INSERT INTO production_baseline VALUES(1,?,?,?)',c.history_sha256,history_json,hash);
    return {status:'PRODUCTION_BASELINE_VERIFIED',replay:!!old};
   });
  },
  async reserve(p){
   const {c,hash}=await scope();
   const expected={request_id:c.request_id,shot_id:c.shot_id,body_sha256:c.body_sha256,draft_sha256:c.draft_sha256,references_sha256:c.references_sha256};
   if(JSON.stringify(p)!==JSON.stringify(expected))fail('EXACT_REQUEST_REQUIRED');
   const token=await sha256('M3_PRODUCTION_V1:'+hash);
   return storage.transactionSync(()=>{
    base(hash);if(one(storage,'SELECT * FROM production_attempt'))fail('ALREADY_RESERVED_NO_RETRY');
    storage.sql.exec("INSERT INTO production_attempt VALUES(1,?,?,?,'SUBMISSION_UNCERTAIN_NO_RETRY',NULL,NULL)",c.request_id,token,JSON.stringify(expected));
    return {status:'SUBMISSION_UNCERTAIN_NO_RETRY',token,dispatch_permitted_once:true};
   });
  },
  async receipt({token,receipt}){
   // Expired dispatch authority MUST NOT prevent reconciliation of saved output.
   if(!HASH.test(token||'')||!receipt||Object.keys(receipt).sort().join(',')!=='accepted,body_sha256,format,height,image_sha256,model,provider_calls,width'||receipt.accepted!==false||receipt.model!==MODEL||receipt.provider_calls!==1||receipt.width!==1024||receipt.height!==576||!['PNG','JPEG','WEBP'].includes(receipt.format)||!HASH.test(receipt.image_sha256||''))fail('RECEIPT_INVALID');
   const raw=JSON.stringify(receipt);
   return storage.transactionSync(()=>{
    const a=current(token);if(JSON.parse(a.spec).body_sha256!==receipt.body_sha256)fail('BODY_CHANGED');
    if(a.receipt&&a.receipt!==raw)fail('RECEIPT_CHANGED');
    if(!a.receipt)storage.sql.exec("UPDATE production_attempt SET phase='RESULT_SAVED_PRIVATE',receipt=? WHERE singleton=1",raw);
    return {status:a.delivery?'DELIVERED_PRIVATE':'RESULT_SAVED_PRIVATE',accepted:false};
   });
  },
  async delivered({token,delivery}){
   if(!delivery||Object.keys(delivery).sort().join(',')!=='image_sha256,journal_sha256,private_storage_verified'||delivery.private_storage_verified!==true||!HASH.test(delivery.journal_sha256||''))fail('DELIVERY_INVALID');
   const raw=JSON.stringify(delivery);
   return storage.transactionSync(()=>{
    const a=current(token);if(!a.receipt||JSON.parse(a.receipt).image_sha256!==delivery.image_sha256)fail('RECEIPT_REQUIRED');
    if(a.delivery&&a.delivery!==raw)fail('DELIVERY_CHANGED');
    if(!a.delivery)storage.sql.exec("UPDATE production_attempt SET phase='DELIVERED_PRIVATE',delivery=? WHERE singleton=1",raw);
    return {status:'DELIVERED_PRIVATE',accepted:false};
   });
  },
  async status(){
   const b=one(storage,'SELECT * FROM production_baseline');const a=one(storage,'SELECT * FROM production_attempt');
   return {status:a?.phase??(b?'PRODUCTION_READY':'PRODUCTION_NOT_INITIALIZED'),baseline_sha256:b?.hash??null,attempt:a??null,dispatch_permitted_once:false};
  },
  async journal(){
   const b=one(storage,'SELECT * FROM production_baseline');if(!b)fail('BASELINE_REQUIRED');
   const h=JSON.parse(b.raw),a=one(storage,'SELECT * FROM production_attempt');
   if(a)h.attempts.push({...JSON.parse(a.spec),key:JSON.parse(a.spec).draft_sha256,status:a.receipt?'RESULT_SAVED_PRIVATE':'SUBMISSION_UNCERTAIN_NO_RETRY',receipt:a.receipt?JSON.parse(a.receipt):null,accepted:false});
   return h;
  }
 };
}
