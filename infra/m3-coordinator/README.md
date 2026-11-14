# M3 SQLite coordinator — executable, but intentionally NOT deployed

This package is the next engineering milestone after [M3's original fail-closed in-memory journal](../../tools/scene_m3_remote.py). It is a real SQLite-backed **Durable Object RPC source**, with a Node 24 test harness executing the same SQL statements against actual SQLite files (including persistence across reopen and two connections competing for one shot). The Worker HTTP entrypoint deliberately returns **404** for every request; no Cloudflare scripts, bindings, paid services, secrets or permissions are created by these files.

## New offline authenticated gateway prototype

`signed-gateway-candidate.mjs` and `worker-gateway-candidate.mjs` are **candidate source files only**; the default `worker.mjs` remains a 404-only entrypoint. Tests use a hard-coded **fake test key** and verify real WebCrypto HMAC-SHA256 over the HTTP method, exact path, UTC timestamp and literal request body. Clock skew, invalid owners, altered signatures, unauthorized operations and server-side missing bindings all fail closed. Only `begin`, `reserve`, `record-fake` and `status` operations are routed, strictly to the same scene-specific Durable Object. No route generates art.

There is **no production HMAC key** and we intentionally did not create one or add a GitHub Actions secret. No authenticated gateway has been deployed. Production rollout would require separate owner confirmation, a scope-limited secret provisioning procedure, and confirmation of Cloudflare Free hard limits and safe quotas. With the current connector, account subscriptions were not readable (HTTP 403), and no Durable Object namespace existed when checked. Therefore no deployment may be considered zero-cost verified yet.

## Boundaries and meaning

- Source: `scene-reservation-core.mjs` exports `createSceneReservationClass(DurableObjectBase)`. `worker.mjs` supplies the Cloudflare base. `scene-reservation.test.mjs` executes the actual SQL with `node:sqlite`. All CI uses no secrets and calls no image endpoint.
- An immutable scene-scoped admission checked by existing `tools/scene_m3_ticket.py` is stored once; source SHA, request ID, baseline legacy journal SHA/count, shot order, shot spec SHA, and hard total attempt ceiling are fixed. No second ticket may take the scene slot. The database is **one Durable Object per scene**, not one object per shot.
- A shot reservation is a single SQLite transaction, before any possible future POST. A crash retains `SUBMISSION_UNCERTAIN_NO_RETRY`, and the next shot cannot begin until an exact deterministic **offline fake** receipt has been recorded. Never retry an ambiguous external image submission. Record fake receipts strictly; no accepted-image claim.
- This is **not yet an operational distributed lock** in the user's account: there has been no deployment, Worker binding, owner HMAC/API access, read-only authentication proof, or trusted copy of the six historical attempts. The existing Drive replacement still lacks verified CAS. Do not confuse tests of actual SQLite with tests of Cloudflare's hosted runtime.
- To connect a future production runner, build a **separately reviewed owner-gated authenticated Worker endpoint**, verify the account is Free with no overage, confirm permissible Workers/DO quotas and allowed secret scope, bootstrap the authoritative history with exact hash while all competing producers are disabled, use the same per-scene object from *every* writer, and test crash/restart/race against a hosted but zero-inference staging instance. Explicit approval required for deployment/provisioning or any live image attempt. Only then consider a real Cloudflare image POST; preserve OPN02/OPN03 as unapproved candidates.
- Until those steps, `generation-safety.json` stays closed and `worker.mjs` has no external API. The 15-second M2 MP4 is a technical fixture, not a finished scene.

## Verify without secrets

```
node --test infra/m3-coordinator/scene-reservation.test.mjs
```

Official documentation checked: [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/), [SQLite storage API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/), [Free plan quotas](https://developers.cloudflare.com/durable-objects/platform/pricing/).

**This work should advance, not replace, the ordinary ChatGPT → owner Issue #54 → GitHub Actions control path and its mandatory scene QA.**
