/** FUTURE deployment candidate, NOT used by worker.mjs or an Actions job.
 * Reviewed implementation needs an out-of-band 256-bit worker secret and
 * Durable Object binding, both deliberately absent. It cannot infer images.
 * Owner approval, account Free/no-charge evidence and staged tests required.
 */
import { DurableObject } from "cloudflare:workers";
import { createSceneReservationClass } from "./scene-reservation-core.mjs";
import { signedOfflineGateway } from "./signed-gateway-candidate.mjs";

export class M3SceneReservation extends createSceneReservationClass(DurableObject) {}

export default {
  async fetch(request,env) {
    return signedOfflineGateway(request,env);
  }
};
