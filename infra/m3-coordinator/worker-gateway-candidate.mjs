/** FUTURE deployment candidate, NOT used by worker.mjs or an Actions job.
 * Reviewed implementation needs an out-of-band 256-bit worker secret and
 * Durable Object binding, both deliberately absent. It cannot infer images.
 * Owner approval, account Free/no-charge evidence and staged tests required.
 */
import { DurableObject } from "cloudflare:workers";
import { createSceneReservationClass } from "./scene-reservation-core.mjs";
import { signedOfflineGateway } from "./signed-gateway-candidate.mjs";
import {chatgptRequest} from './chatgpt-mcp.mjs';
import {authStorage,bridgeJobs} from './chatgpt-store.mjs';

export class M3SceneReservation extends createSceneReservationClass(DurableObject) {
  async chatgptAuth(operation,payload){
    const store=authStorage(this.ctx.storage);
    if(operation==='get')return store.get(payload.key);
    if(operation==='put')return store.put(payload.key,payload.value,payload.options);
    if(operation==='delete')return store.delete(payload.key);
    if(operation==='list')return store.list(payload);
    if(operation==='approvePending')return store.approvePending(payload.id);
    throw Error('AUTH_OPERATION_DENIED');
  }
  async chatgptJob(operation,id){
    const jobs=bridgeJobs(this.ctx.storage,this.env);
    if(operation==='enqueue')return jobs.enqueue(id);
    if(operation==='get')return jobs.get(id);
    throw Error('JOB_OPERATION_DENIED');
  }
  async alarm(){await bridgeJobs(this.ctx.storage,this.env).alarm();}
}

export default {
  async fetch(request,env,ctx) {
    const chatgpt=await chatgptRequest(request,env,ctx);
    if(chatgpt)return chatgpt;
    return signedOfflineGateway(request,env);
  }
};
