/** Candidate HTTP gateway for the disconnected M3 SQLite Durable Object.
 *
 * NOT REFERENCED BY CURRENT CLOUDFLARE DEPLOYMENT. The default worker.mjs
 * still returns 404. Deploy/use only after owner-specific permission,
 * account Free hard-cap verification, secret provisioning and full QA.
 *
 * Every accepted request is HMAC-signed using an out-of-band 256-bit secret.
 * No read-only endpoint is publicly accessible; no model or Drive calls.
 */
const OWNER="barkinam21-pixel";
// All legacy OPN scenes share ONE private Drive journal. A scene-keyed DO
// would wrongly allow separate atomic budgets against the same history.
// This candidate intentionally binds only one scene until reviewed migration.
const SHARED_JOURNAL_SCOPE="M3-LEGACY-SHARED-JOURNAL-V1";
const ENDPOINT="/m3/v1/offline";
const HEX=/^[a-f0-9]+$/;
const SCENE=/^[A-Z0-9][A-Z0-9-]{2,79}$/;
const MAX_BYTES=32768;
const FIVE_MIN=300000;
const ONE_MIN=60000;
const te=new TextEncoder();

function reply(status,body) {
  return Response.json(body,{status,headers:{"Cache-Control":"no-store"}});
}
function bytesHex(hex) {
  return Uint8Array.from(hex.match(/.{2}/g), x=>parseInt(x,16));
}
function constTimeEqual(a,b) {
  if(a.length!==b.length) return false;
  let d=0;
  for(let i=0;i<a.length;i++) d|=(a[i]^b[i]);
  return d===0;
}
async function signed(secret, message) {
  const k=await crypto.subtle.importKey("raw",bytesHex(secret),
    {name:"HMAC",hash:"SHA-256"},false,["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC",k,te.encode(message)));
}
export async function createSignatureForTesting(secret,timestamp,body) {
  // Public helper contains no secret. Do not embed a production key in code.
  const sig=await signed(secret,"POST\n"+ENDPOINT+"\n"+timestamp+"\n"+body);
  return [...sig].map(x=>x.toString(16).padStart(2,"0")).join("");
}

export async function signedOfflineGateway(request,env,{now=Date.now()}={}) {
  try {
    const path=new URL(request.url).pathname;
    const production=path==="/m3/v1/production";
    if((path!==ENDPOINT && !production) || request.method!=="POST")
      return reply(404,{status:"NOT_FOUND"});
    // Never report "unauthorized" as success or fall through to a live route.
    if(typeof env?.M3_GATEWAY_HMAC_KEY!=="string" ||
       !/^[a-f0-9]{64}$/.test(env.M3_GATEWAY_HMAC_KEY) ||
       !env.M3_SCENE_RESERVATION?.getByName)
      return reply(503,{status:"DISABLED_NO_AUTHENTICATED_COORDINATOR"});
    // Real private six-attempt Drive journal is ~49KB; offline limit stays32KB.
    const maxBytes=production?2_000_000:MAX_BYTES;
    const length=request.headers.get("content-length");
    if(length!==null && (!/^\d+$/.test(length) || Number(length)>maxBytes))
      return reply(413,{status:"REQUEST_TOO_LARGE"});
    const raw=await request.text();
    if(te.encode(raw).length>maxBytes)
      return reply(413,{status:"REQUEST_TOO_LARGE"});
    const timestamp=request.headers.get("x-m3-timestamp");
    const signature=request.headers.get("x-m3-signature");
    if(!timestamp || !signature || !/^[a-f0-9]{64}$/.test(signature))
      return reply(401,{status:"UNAUTHORIZED"});
    const millis=Date.parse(timestamp);
    if(!Number.isFinite(millis) || millis<now-FIVE_MIN || millis>now+ONE_MIN)
      return reply(401,{status:"UNAUTHORIZED"});
    const expected=await signed(env.M3_GATEWAY_HMAC_KEY,
      "POST\n"+path+"\n"+timestamp+"\n"+raw);
    if(!constTimeEqual(expected,bytesHex(signature)))
      return reply(401,{status:"UNAUTHORIZED"});
    let envelope;
    try {envelope=JSON.parse(raw);} catch {return reply(400,{status:"INVALID_JSON"});}
    if(!envelope || typeof envelope!=="object" ||
       Object.keys(envelope).sort().join(",")!=="operation,owner,payload,scene_id,version" ||
       envelope.version!==1 || envelope.owner!==OWNER ||
       !SCENE.test(envelope.scene_id||""))
      return reply(403,{status:"OWNER_SCOPE_INVALID"});
    const operation=envelope.operation, payload=envelope.payload;
    if(production){
      if(envelope.scene_id!=="ACT1-PROLOGUE" || !['bootstrap','reserve','receipt','delivered','status','journal'].includes(operation) || !payload || typeof payload!=="object" || Array.isArray(payload))
        return reply(403,{status:"PRODUCTION_SCOPE_INVALID"});
      // SAME namespace, DIFFERENT persistent singleton; never mutate canary.
      const stub=env.M3_SCENE_RESERVATION.getByName("M3-PRODUCTION-SHARED-JOURNAL-V1");
      try {return reply(200,await stub.production(operation,payload));}
      catch {return reply(409,{status:"M3_PRODUCTION_REJECTED_NO_RETRY"});}
    }
    if(!["begin","reserve","record-fake","status"].includes(operation) ||
       !payload || typeof payload!=="object" || Array.isArray(payload))
      return reply(400,{status:"OPERATION_NOT_ALLOWED"});
    if(operation==="begin" && payload.scene_id!==envelope.scene_id)
      return reply(403,{status:"SCENE_MISMATCH"});
    const stub=env.M3_SCENE_RESERVATION.getByName(SHARED_JOURNAL_SCOPE);
    if(operation!=="begin"){
      // Do not allow cross-scene status inspection or a forged scene envelope
      // to use another scene's otherwise valid request_id.
      const bound=await stub.inspectOffline();
      if(bound.status!=="NOT_INITIALIZED" && bound.scene_id!==envelope.scene_id)
        return reply(409,{status:"M3_COORDINATOR_REJECTED_NO_RETRY"});
    }
    let result;
    try {
      if(operation==="begin") result=await stub.beginOffline(payload);
      else if(operation==="reserve") result=await stub.reserveOffline(payload);
      else if(operation==="record-fake") result=await stub.recordFakeReceipt(payload);
      else result=await stub.inspectOffline();
    } catch {
      // Fail closed and never expose internal journal/asset/authorization data.
      return reply(409,{status:"M3_COORDINATOR_REJECTED_NO_RETRY"});
    }
    // A status call may race with the first admission: verify its scope again.
    if(operation==="status" && result.status!=="NOT_INITIALIZED" &&
       result.scene_id!==envelope.scene_id)
      return reply(409,{status:"M3_COORDINATOR_REJECTED_NO_RETRY"});
    if(result?.live_dispatch_enabled!==false)
      return reply(500,{status:"LIVE_GATE_NOT_DISABLED"});
    return reply(200,result);
  } catch {
    return reply(500,{status:"M3_GATEWAY_ERROR_NO_RETRY"});
  }
}
