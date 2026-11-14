/** DISCONNECTED M3 Coordinator Cloudflare Worker entrypoint.
 * No public route, no credentials, no inference, no Drive or asset access.
 * This file is source control only. No deployment/config/bindings created.
 * An authenticated owner-gated gateway and account-level privacy + Free
 * evidence are required before any live integration.
 */
import { DurableObject } from "cloudflare:workers";
import { createSceneReservationClass } from "./scene-reservation-core.mjs";

export class M3SceneReservation extends createSceneReservationClass(DurableObject) {}

// Production hostname should not expose any mutation or read endpoint.
export default {
  async fetch() {
    return new Response("Not Found", {
      status:404,
      headers:{"Cache-Control":"no-store","Content-Type":"text/plain;charset=utf-8"}
    });
  }
};
