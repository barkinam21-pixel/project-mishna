/** M3 Durable Object reservation core, disconnected from image inference.
 *
 * This uses real SQLite transactions; no Drive-as-CAS assumption. It exposes
 * OFFLINE RPC methods only. Importing the module never contacts Cloudflare.
 * A separate reviewed/authenticated gateway and migration are required before
 * any live producer is wired to it. Keep the existing generation gate CLOSED.
 */
const HEX32 = /^[a-f0-9]{32}$/;
const HEX64 = /^[a-f0-9]{64}$/;
const SCENE = /^[A-Z0-9][A-Z0-9-]{2,79}$/;
const SHOT = /^[A-Z0-9][A-Z0-9-]{2,79}$/;

function deny(code) { throw new Error("M3_DO_" + code); }
function rows(sql, statement, ...params) { return sql.exec(statement, ...params).toArray(); }
function single(sql, statement, ...params) { return rows(sql, statement, ...params)[0] ?? null; }
const canonical = value => JSON.stringify(value);

export async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
}

export function validateOfflineAdmission(a) {
  if (!a || typeof a !== "object" || Array.isArray(a)) deny("ADMISSION_INVALID");
  if (a.status !== "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH" ||
      a.live_dispatch_enabled !== false || a.max_charge_usd !== 0)
    deny("LIVE_PRODUCTION_FORBIDDEN");
  if (!SCENE.test(a.scene_id || "") || !HEX32.test(a.request_id || "") ||
      !HEX64.test(a.history_sha256 || "")) deny("SCOPE_IDENTIFIER_INVALID");
  if (!Number.isInteger(a.historical_attempts) || a.historical_attempts < 6 ||
      !Number.isInteger(a.max_attempts) || a.max_attempts < 1 ||
      !Array.isArray(a.shot_ids) || a.shot_ids.length < 1 ||
      a.shot_ids.length > 25 || a.max_attempts > a.shot_ids.length ||
      a.total_attempt_limit !== a.historical_attempts + a.max_attempts)
    deny("ATTEMPT_SCOPE_INVALID");
  if (new Set(a.shot_ids).size !== a.shot_ids.length ||
      a.shot_ids.some(s => typeof s !== "string" || !SHOT.test(s)))
    deny("SHOT_LIST_INVALID");
  if (!a.asset_keys || typeof a.asset_keys !== "object" ||
      Array.isArray(a.asset_keys) ||
      Object.keys(a.asset_keys).length !== a.shot_ids.length ||
      a.shot_ids.some(s => !HEX64.test(a.asset_keys[s] || "")) ||
      Object.keys(a.asset_keys).some(k => !a.shot_ids.includes(k)))
    deny("ASSET_KEYS_INVALID");
  // Sorting makes JS's serialisation immune to external object key order.
  const sortedKeys = Object.fromEntries(a.shot_ids.map(id => [id, a.asset_keys[id]]));
  return {
    scene_id: a.scene_id, request_id: a.request_id,
    history_sha256: a.history_sha256, historical_attempts: a.historical_attempts,
    max_attempts: a.max_attempts, total_attempt_limit: a.total_attempt_limit,
    shot_ids: [...a.shot_ids], asset_keys: sortedKeys,
    max_charge_usd: 0, live_dispatch_enabled: false
  };
}

const DDL = [
  `CREATE TABLE IF NOT EXISTS scene_scope (
     singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
     scene_id TEXT NOT NULL, request_id TEXT NOT NULL,
     scope_hash TEXT NOT NULL, baseline_sha256 TEXT NOT NULL,
     baseline_attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
     total_attempt_limit INTEGER NOT NULL,
     shot_ids_json TEXT NOT NULL, asset_keys_json TEXT NOT NULL,
     stage TEXT NOT NULL CHECK(stage IN ('OFFLINE_READY','OFFLINE_PARTIAL','OFFLINE_COMPLETE'))
   )`,
  `CREATE TABLE IF NOT EXISTS reservations (
     ordinal INTEGER PRIMARY KEY CHECK(ordinal >= 1),
     request_id TEXT NOT NULL, shot_id TEXT NOT NULL UNIQUE,
     spec_sha256 TEXT NOT NULL, token TEXT NOT NULL UNIQUE,
     outcome TEXT NOT NULL CHECK(outcome IN ('SUBMISSION_UNCERTAIN_NO_RETRY','OFFLINE_FAKE_RECEIPT')),
     fake_receipt_sha256 TEXT
   )`
];

export function createSceneReservationClass(DurableObjectBase) {
  return class SceneReservation extends DurableObjectBase {
    constructor(ctx, env) {
      super(ctx, env);
      ctx.blockConcurrencyWhile(async () => {
        for (const stmt of DDL) ctx.storage.sql.exec(stmt);
      });
    }

    // RPC. Intentionally does not authorize an external generation call.
    async beginOffline(admission) {
      const spec = validateOfflineAdmission(admission);
      const scopeHash = await sha256(canonical(spec));
      const storage = this.ctx.storage;
      return storage.transactionSync(() => {
        const existing = single(storage.sql, "SELECT * FROM scene_scope WHERE singleton=1");
        if (existing) {
          if (existing.scene_id !== spec.scene_id ||
              existing.request_id !== spec.request_id ||
              existing.scope_hash !== scopeHash)
            deny("SCENE_ALREADY_BOUND_OR_CHANGED");
          return {status: existing.stage, replay: true,
                  request_id: spec.request_id, live_dispatch_enabled: false};
        }
        storage.sql.exec(
          `INSERT INTO scene_scope
           (singleton,scene_id,request_id,scope_hash,baseline_sha256,
            baseline_attempts,max_attempts,total_attempt_limit,
            shot_ids_json,asset_keys_json,stage)
           VALUES (1,?,?,?,?,?,?,?,?,?,'OFFLINE_READY')`,
          spec.scene_id, spec.request_id, scopeHash, spec.history_sha256,
          spec.historical_attempts, spec.max_attempts, spec.total_attempt_limit,
          canonical(spec.shot_ids), canonical(spec.asset_keys)
        );
        return {status: "OFFLINE_READY", replay: false,
                request_id: spec.request_id, live_dispatch_enabled: false};
      });
    }

    async reserveOffline({request_id,shot_id}) {
      if (!HEX32.test(request_id || "") || !SHOT.test(shot_id || ""))
        deny("RESERVATION_INPUT_INVALID");
      const storage=this.ctx.storage;
      const scope = single(storage.sql,"SELECT * FROM scene_scope WHERE singleton=1");
      if (!scope || scope.request_id !== request_id) deny("SCOPE_NOT_FOUND");
      const shotIds=JSON.parse(scope.shot_ids_json);
      const specMap=JSON.parse(scope.asset_keys_json);
      // No I/O inside the critical SQL transaction. Hash is calculated first,
      // then all scope/race checks are repeated in transactionSync.
      const ordinal = rows(storage.sql,"SELECT ordinal FROM reservations ORDER BY ordinal").length+1;
      const nextShot=shotIds[ordinal-1];
      if (!nextShot || nextShot !== shot_id) deny("SHOT_NOT_NEXT_OR_REPLAY");
      const token=await sha256("M3_DO_V1:"+scope.scope_hash+":"+shot_id+":"+specMap[shot_id]);
      return storage.transactionSync(() => {
        const latest=single(storage.sql,"SELECT * FROM scene_scope WHERE singleton=1");
        if (!latest || latest.scope_hash!==scope.scope_hash ||
            latest.request_id!==request_id) deny("SCOPE_CHANGED");
        const reservations=rows(storage.sql,
                                "SELECT ordinal,shot_id,outcome FROM reservations ORDER BY ordinal");
        if (reservations.length>=latest.max_attempts ||
            latest.baseline_attempts+reservations.length >= latest.total_attempt_limit)
          deny("HARD_ATTEMPT_LIMIT");
        if (shotIds[reservations.length]!==shot_id) deny("SHOT_NOT_NEXT_OR_REPLAY");
        if (reservations.length>0 &&
            reservations[reservations.length-1].outcome!=="OFFLINE_FAKE_RECEIPT")
          deny("PREVIOUS_ATTEMPT_UNCERTAIN");
        storage.sql.exec(
          `INSERT INTO reservations
            (ordinal,request_id,shot_id,spec_sha256,token,outcome)
           VALUES (?,?,?,?,?,'SUBMISSION_UNCERTAIN_NO_RETRY')`,
          reservations.length+1,request_id,shot_id,specMap[shot_id],token
        );
        return {status:"OFFLINE_RESERVED_UNCERTAIN_NO_RETRY",
                shot_id, ordinal:reservations.length+1, token,
                external_inference_requests:0,live_dispatch_enabled:false};
      });
    }

    async recordFakeReceipt({request_id,shot_id,receipt}) {
      if (!HEX32.test(request_id || "") || !SHOT.test(shot_id || ""))
        deny("RECEIPT_INPUT_INVALID");
      const storage=this.ctx.storage;
      const scope=single(storage.sql,"SELECT * FROM scene_scope WHERE singleton=1");
      if (!scope || scope.request_id!==request_id) deny("SCOPE_NOT_FOUND");
      const specs=JSON.parse(scope.asset_keys_json);
      const fakeHash=await sha256(
        "M3_FAKE_IMAGE_V1:"+scope.scene_id+":"+shot_id+":"+specs[shot_id]
      );
      if (!receipt || Object.keys(receipt).sort().join(",") !==
          "accepted,external_cost_usd,kind,provider_calls,sha256" ||
          receipt.kind!=="OFFLINE_FAKE_NOT_IMAGE" ||
          receipt.sha256!==fakeHash || receipt.accepted!==false ||
          receipt.provider_calls!==0 || receipt.external_cost_usd!==0)
        deny("FAKE_RECEIPT_INVALID");
      return storage.transactionSync(() => {
        const latest=single(storage.sql,"SELECT * FROM scene_scope WHERE singleton=1");
        if (!latest || latest.scope_hash!==scope.scope_hash) deny("SCOPE_CHANGED");
        const last=single(storage.sql,
                          "SELECT * FROM reservations ORDER BY ordinal DESC LIMIT 1");
        if (!last || last.shot_id!==shot_id || last.request_id!==request_id ||
            last.outcome!=="SUBMISSION_UNCERTAIN_NO_RETRY" ||
            last.spec_sha256!==specs[shot_id])
          deny("NO_MATCHING_UNCERTAIN_RESERVATION");
        storage.sql.exec(
          "UPDATE reservations SET outcome='OFFLINE_FAKE_RECEIPT',fake_receipt_sha256=? WHERE ordinal=?",
          fakeHash,last.ordinal
        );
        const stage=last.ordinal>=scope.max_attempts?"OFFLINE_COMPLETE":"OFFLINE_PARTIAL";
        storage.sql.exec("UPDATE scene_scope SET stage=? WHERE singleton=1",stage);
        return {status:stage,shot_id,accepted:false,live_dispatch_enabled:false};
      });
    }

    async inspectOffline() {
      const scope=single(this.ctx.storage.sql,"SELECT * FROM scene_scope WHERE singleton=1");
      if (!scope) return {status:"NOT_INITIALIZED",live_dispatch_enabled:false};
      const attempts=rows(this.ctx.storage.sql,
                          "SELECT ordinal,request_id,shot_id,spec_sha256,token,outcome,fake_receipt_sha256 FROM reservations ORDER BY ordinal");
      return {status:scope.stage,request_id:scope.request_id,scene_id:scope.scene_id,
              baseline_attempts:scope.baseline_attempts,
              baseline_sha256:scope.baseline_sha256,
              attempts,live_dispatch_enabled:false,external_inference_requests:0,
              // Interrupted reservation ALWAYS needs manual reconciliation.
              requires_review: attempts.some(x=>x.outcome==="SUBMISSION_UNCERTAIN_NO_RETRY")};
    }
  };
}
