/** Private OAuth records and connection jobs in the EXISTING namespace. */
const safeId = v => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v);
const row = (s, q, ...a) => s.sql.exec(q, ...a).toArray()[0];

export function authStorage(storage) {
  storage.sql.exec('CREATE TABLE IF NOT EXISTS chatgpt_oauth (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires INTEGER)');
  return {
    get(key) {
      const v = row(storage, 'SELECT value,expires FROM chatgpt_oauth WHERE key=?', key);
      return v && (!v.expires || v.expires > Date.now()) ? v.value : null;
    },
    put(key, value, options = {}) {
      if (typeof key !== 'string' || key.length > 2048 || typeof value !== 'string' || value.length > 262144)
        throw Error('OAUTH_RECORD_TOO_LARGE');
      const expires = options.expiration ? options.expiration * 1000 : options.expirationTtl ? Date.now() + options.expirationTtl * 1000 : null;
      storage.sql.exec('DELETE FROM chatgpt_oauth WHERE expires IS NOT NULL AND expires<=?', Date.now());
      if (!row(storage, 'SELECT key FROM chatgpt_oauth WHERE key=?', key) && row(storage, 'SELECT count(*) n FROM chatgpt_oauth').n >= 2048)
        throw Error('OAUTH_STORE_LIMIT');
      storage.sql.exec('INSERT INTO chatgpt_oauth VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,expires=excluded.expires', key, value, expires);
    },
    delete(key) { storage.sql.exec('DELETE FROM chatgpt_oauth WHERE key=?', key); },
    list({prefix = '', limit = 1000, cursor = ''} = {}) {
      const n = Math.min(Math.max(Number(limit) || 1000, 1), 1000);
      const found = storage.sql.exec('SELECT key,expires FROM chatgpt_oauth WHERE key>=? AND key<? AND key>? AND (expires IS NULL OR expires>?) ORDER BY key LIMIT ?', prefix, prefix + '\uffff', cursor, Date.now(), n + 1).toArray();
      return {keys:found.slice(0,n).map(v=>({name:v.key,...(v.expires?{expiration:Math.floor(v.expires/1000)}:{})})),list_complete:found.length<=n,cursor:found.length>n?found[n-1].key:''};
    },
    approvePending(id) {
      if (!safeId(id)) throw Error('PENDING_ID_INVALID');
      return storage.transactionSync(() => {
        const p = this.get('pending:' + id);
        if (!p) throw Error('PENDING_EXPIRED');
        const v = JSON.parse(p);
        this.put('pending:' + id, JSON.stringify({...v, ownerApproved:true}), {expirationTtl:300});
        return {status:'CONNECTION_CONSENT_READY',pending_id:id};
      });
    }
  };
}

export class DurableOAuthKV {
  constructor(namespace) { this.stub = namespace.getByName('M3-CHATGPT-AUTH-V1'); }
  async get(key, options) {
    const v = await this.stub.chatgptAuth('get', {key});
    const kind = typeof options === 'string' ? options : options?.type;
    return v === null ? null : kind === 'json' ? JSON.parse(v) : kind === 'arrayBuffer' ? new TextEncoder().encode(v).buffer : v;
  }
  async put(key, value, options) { await this.stub.chatgptAuth('put', {key,value,options}); }
  async delete(key) { await this.stub.chatgptAuth('delete', {key}); }
  async list(options) { return this.stub.chatgptAuth('list', options || {}); }
}

export function bridgeJobs(storage, env) {
  storage.sql.exec('CREATE TABLE IF NOT EXISTS chatgpt_connection_jobs (id TEXT PRIMARY KEY, phase TEXT NOT NULL, result TEXT, created INTEGER NOT NULL)');
  return {
    async enqueue(id) {
      if (!safeId(id)) throw Error('JOB_ID_INVALID');
      const old = row(storage, 'SELECT phase FROM chatgpt_connection_jobs WHERE id=?', id);
      if (old) return {request_id:id,status:old.phase,replay:true,inference_requests:0};
      if (row(storage,'SELECT count(*) n FROM chatgpt_connection_jobs').n>=100) throw Error('CONNECTION_JOB_LIMIT');
      // Commit the durable alarm BEFORE returning. Replayed POST cannot create a second job.
      await storage.transaction(async () => {
        storage.sql.exec("INSERT INTO chatgpt_connection_jobs VALUES(?,'QUEUED',NULL,?)", id, Date.now());
        await storage.setAlarm(Date.now() + 10);
      });
      return {request_id:id,status:'QUEUED',replay:false,inference_requests:0};
    },
    get(id) {
      if (!safeId(id)) throw Error('JOB_ID_INVALID');
      const v=row(storage,'SELECT phase,result FROM chatgpt_connection_jobs WHERE id=?',id);
      return v?{request_id:id,status:v.phase,result:v.result?JSON.parse(v.result):null}:{status:'JOB_NOT_FOUND'};
    },
    async alarm() {
      // This job deliberately has NO AI call or external storage mutation.
      const jobs=storage.sql.exec("SELECT id FROM chatgpt_connection_jobs WHERE phase='QUEUED' ORDER BY created LIMIT 10").toArray();
      for (const job of jobs) {
        const s=await env.M3_SCENE_RESERVATION.getByName('M3-PRODUCTION-SHARED-JOURNAL-V1').production('status',{});
        const result={status:'CLOUD_CONNECTION_CHECK_COMPLETE',m3_status:s.status,atomic_reservation_present:!!s.attempt,production_scope_configured:typeof env.M3_PRODUCTION_CONFIG==='string',private_drive_credential_mounted:typeof env.MISHNAH_DRIVE_OAUTH_JSON==='string',native_ai_binding_present:!!env.AI,permanent_image_executor_ready:false,inference_requests:0};
        storage.sql.exec("UPDATE chatgpt_connection_jobs SET phase='COMPLETE',result=? WHERE id=? AND phase='QUEUED'",JSON.stringify(result),job.id);
      }
      if (row(storage,"SELECT id FROM chatgpt_connection_jobs WHERE phase='QUEUED'")) await storage.setAlarm(Date.now()+10);
    }
  };
}
