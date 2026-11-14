/** OFFLINE ONLY: immutable import and reconciliation of a shared legacy journal.
 *
 * This module is deliberately NOT exported by the HTTP gateway or default
 * Worker. The caller must supply a separately trusted private-history reader.
 * A ticket-supplied digest is NEVER proof that private Drive was read.
 * Even a passing offline reconciliation cannot authorize a provider call:
 * Drive media replace is not CAS, and hosted writer exclusion is unproven.
 */
import {sha256,validateOfflineAdmission} from "./scene-reservation-core.mjs";

function deny(code){throw Error("M3_LEGACY_"+code);}
function rows(s,q,...args){return s.sql.exec(q,...args).toArray();}
function one(s,q,...args){return rows(s,q,...args)[0]??null;}

// Match the existing Python json.dumps(sort_keys=True,separators=(",",":"))
// digest for representable JSON. If a legacy float has a different Python
// lexical representation (e.g. 0.0), the mismatch must BLOCK, never be waived.
export function legacyCanonicalJSON(value){
  const sort=(v)=>{
    if(v===null || typeof v==="string" || typeof v==="boolean") return v;
    if(typeof v==="number" && Number.isFinite(v)) return v;
    if(Array.isArray(v)) return v.map(sort);
    if(v && typeof v==="object" && Object.getPrototypeOf(v)===Object.prototype)
      return Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])]));
    deny("NON_JSON_HISTORY");
  };
  const json=JSON.stringify(sort(value));
  if(typeof json!=="string") deny("NON_JSON_HISTORY");
  return json.replace(/[\u007f-\uffff]/g,
    ch=>"\\u"+ch.charCodeAt(0).toString(16).padStart(4,"0"));
}

const DDL=[
  `CREATE TABLE IF NOT EXISTS legacy_history_bootstrap (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    baseline_sha256 TEXT NOT NULL,
    attempts INTEGER NOT NULL CHECK(attempts>=6),
    canonical_json TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK(provenance='OFFLINE_FIXTURE_NO_REMOTE_PROOF')
  )`,
  `CREATE TABLE IF NOT EXISTS legacy_history_attempts (
    ordinal INTEGER PRIMARY KEY CHECK(ordinal>=1),
    content_sha256 TEXT NOT NULL,
    canonical_json TEXT NOT NULL
  )`
];

async function readAndVerify(admission,readPrivateHistory){
  const spec=validateOfflineAdmission(admission);
  if(typeof readPrivateHistory!=="function")
    deny("INDEPENDENT_PRIVATE_READER_REQUIRED");
  // Read via a separate injected source; never use ticket-supplied history.
  const history=await readPrivateHistory();
  if(!history || typeof history!=="object" || Array.isArray(history) ||
     !Array.isArray(history.attempts) || history.attempts.length!==spec.historical_attempts ||
     history.attempts.length<6 || history.attempts.some(a=>
       !a || typeof a!=="object" || Array.isArray(a)))
    deny("SIX_ATTEMPT_HISTORY_INVALID");
  const canonical=legacyCanonicalJSON(history);
  const digest=await sha256(canonical);
  if(digest!==spec.history_sha256) deny("STALE_OR_FORGED_BASELINE");
  // Copy exact full object (including candidate decisions/unknown metadata).
  const entries=await Promise.all(history.attempts.map(async(a,i)=>{
    const record=legacyCanonicalJSON(a);
    return {ordinal:i+1,canonical:record,digest:await sha256(record)};
  }));
  const ids=history.attempts.map(x=>x.request_id).filter(x=>x!==undefined);
  if(ids.some(x=>typeof x!=="string") || new Set(ids).size!==ids.length)
    deny("DUPLICATE_OR_INVALID_HISTORICAL_REQUEST_ID");
  if(ids.includes(spec.request_id)) deny("REQUEST_ALREADY_IN_HISTORY_NO_RETRY");
  return {spec,canonical,digest,entries};
}

function assertStored(storage,prepared){
  const meta=one(storage,"SELECT * FROM legacy_history_bootstrap WHERE singleton=1");
  if(!meta) deny("MIGRATION_MISSING");
  if(meta.baseline_sha256!==prepared.digest ||
     meta.attempts!==prepared.entries.length ||
     meta.canonical_json!==prepared.canonical ||
     meta.provenance!=="OFFLINE_FIXTURE_NO_REMOTE_PROOF")
    deny("WRITER_CONFLICT_OR_OVERWRITE");
  const entries=rows(storage,
    "SELECT ordinal,content_sha256,canonical_json FROM legacy_history_attempts ORDER BY ordinal");
  if(entries.length!==prepared.entries.length ||
     entries.some((row,i)=>row.ordinal!==prepared.entries[i].ordinal ||
       row.content_sha256!==prepared.entries[i].digest ||
       row.canonical_json!==prepared.entries[i].canonical))
    deny("MIGRATED_PREFIX_CORRUPTED");
}

export function createOfflineLegacyReconciler(storage){
  if(!storage?.sql?.exec || !storage?.transactionSync)
    deny("ATOMIC_STORAGE_REQUIRED");
  for(const statement of DDL) storage.sql.exec(statement);
  function assertScope(spec){
    const scope=one(storage,"SELECT * FROM scene_scope WHERE singleton=1");
    if(!scope || scope.scene_id!==spec.scene_id ||
       scope.request_id!==spec.request_id ||
       scope.baseline_sha256!==spec.history_sha256 ||
       scope.baseline_attempts!==spec.historical_attempts ||
       scope.total_attempt_limit!==spec.total_attempt_limit)
      deny("COORDINATOR_SCOPE_MISMATCH");
  }
  return {
    async bootstrapOffline({admission,readPrivateHistory,failAfterInsert=false}){
      const prepared=await readAndVerify(admission,readPrivateHistory);
      return storage.transactionSync(()=>{
        assertScope(prepared.spec);
        if(one(storage,"SELECT ordinal FROM reservations LIMIT 1"))
          deny("RESERVATION_ALREADY_STARTED_NO_MIGRATION");
        const existing=one(storage,
          "SELECT singleton FROM legacy_history_bootstrap WHERE singleton=1");
        if(existing){
          assertStored(storage,prepared);
          return {status:"OFFLINE_PREFIX_IDENTICAL_NO_LIVE_PROOF",replay:true,
            historical_attempts:prepared.entries.length,live_dispatch_enabled:false};
        }
        storage.sql.exec(
          "INSERT INTO legacy_history_bootstrap VALUES (1,?,?,?,'OFFLINE_FIXTURE_NO_REMOTE_PROOF')",
          prepared.digest,prepared.entries.length,prepared.canonical
        );
        for(const entry of prepared.entries)
          storage.sql.exec("INSERT INTO legacy_history_attempts VALUES (?,?,?)",
            entry.ordinal,entry.digest,entry.canonical);
        // Deterministic fault injection: SQL transaction must roll back ALL
        // rows even if a worker dies between writing metadata and COMMIT.
        if(failAfterInsert) deny("SIMULATED_CRASH_BEFORE_COMMIT");
        return {status:"OFFLINE_PREFIX_IMPORTED_NO_LIVE_PROOF",replay:false,
          historical_attempts:prepared.entries.length,live_dispatch_enabled:false};
      });
    },
    async reconcileOffline({admission,readPrivateHistory}){
      const prepared=await readAndVerify(admission,readPrivateHistory);
      return storage.transactionSync(()=>{
        assertScope(prepared.spec);
        assertStored(storage,prepared);
        const reservations=rows(storage,"SELECT outcome FROM reservations ORDER BY ordinal");
        return {status:"OFFLINE_PREFIX_MATCH_NO_REMOTE_CAS",
          historical_attempts:prepared.entries.length,
          offline_reservations:reservations.length,
          requires_review:reservations.some(x=>x.outcome==="SUBMISSION_UNCERTAIN_NO_RETRY"),
          live_dispatch_enabled:false,provider_submission_authorized:false};
      });
    }
  };
}
