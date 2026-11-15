// Test-only subprocess adapter: real persistent SQLite, synthetic config/history.
import {DatabaseSync} from 'node:sqlite';
import {productionMethods} from '../../infra/m3-coordinator/production-ledger.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const {path,config,operation,payload}=JSON.parse(input);
const db=new DatabaseSync(path);db.exec('PRAGMA busy_timeout=1000');
const storage={sql:{exec(q,...a){const rows=db.prepare(q).all(...a);return {toArray:()=>rows};}},transactionSync(fn){db.exec('BEGIN IMMEDIATE');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}}};
try{const api=productionMethods(storage,{M3_PRODUCTION_CONFIG:JSON.stringify(config)});console.log(JSON.stringify(await api[operation](payload)));}catch(e){console.log(JSON.stringify({error:e.message}));process.exitCode=2;}finally{db.close();}
