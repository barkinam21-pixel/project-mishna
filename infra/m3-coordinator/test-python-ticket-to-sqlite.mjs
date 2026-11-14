/** No-network bridge test: feed the real Python owner ticket validator's output
 * into the SQLite Durable Object core. This is NOT an authenticated gateway.
 * No public API, no real image call and no attached Cloudflare resources.
 */
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { createSceneReservationClass } from "./scene-reservation-core.mjs";

class Base {
  constructor(ctx,env){this.ctx=ctx;this.env=env;}
}
const Coordinator=createSceneReservationClass(Base);

async function main(){
  const bytes=readFileSync(0);
  if(bytes.length===0 || bytes.length>32768) throw Error("M3_BRIDGE_INPUT_SIZE_INVALID");
  const admission=JSON.parse(bytes.toString("utf8"));
  const db=new DatabaseSync(":memory:");
  try {
    const ctx={
      storage:{
        sql:{
          exec(statement,...params) {
            const result=db.prepare(statement).all(...params);
            return {toArray:()=>result};
          }
        },
        transactionSync(fn){
          db.exec("BEGIN IMMEDIATE");
          try {const r=fn();db.exec("COMMIT");return r;}
          catch(e){db.exec("ROLLBACK");throw e;}
        }
      },
      blockConcurrencyWhile(fn){
        this.ready=Promise.resolve(fn());
        return this.ready;
      }
    };
    const q=new Coordinator(ctx,{});
    await ctx.ready;
    const planned=await q.beginOffline(admission);
    const reserved=await q.reserveOffline({
      request_id:admission.request_id,
      shot_id:admission.shot_ids[0]
    });
    const state=await q.inspectOffline();
    if(planned.status!=="OFFLINE_READY" ||
       reserved.status!=="OFFLINE_RESERVED_UNCERTAIN_NO_RETRY" ||
       state.attempts.length!==1 ||
       state.baseline_attempts!==admission.historical_attempts ||
       state.baseline_sha256!==admission.history_sha256 ||
       state.live_dispatch_enabled!==false ||
       state.external_inference_requests!==0 ||
       !state.requires_review)
       throw Error("M3_BRIDGE_RECEIPT_INVARIANT_BROKEN");
    console.log(JSON.stringify({
      status:"OFFLINE_VERIFIED_OWNER_TICKET_REACHED_SQLITE",
      scene_id:admission.scene_id,
      historical_attempts:state.baseline_attempts,
      new_reserved_attempts:state.attempts.length,
      request_id:admission.request_id,
      live_dispatch_enabled:false,
      external_inference_requests:0,
      requires_review:true
    }));
  } finally {db.close();}
}
try {await main();}
catch(e) {
  console.log(JSON.stringify({
    status:"BLOCKED",reason:String(e.message||"M3_BRIDGE_ERROR").slice(0,140),
    live_dispatch_enabled:false,external_inference_requests:0
  }));
  process.exitCode=2;
}
