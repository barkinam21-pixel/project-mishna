# M3 SQLite coordinator — executable, but intentionally NOT deployed

This package is the next engineering milestone after [M3's original fail-closed in-memory journal](../../tools/scene_m3_remote.py). It is a real SQLite-backed **Durable Object RPC source**, with a Node 24 test harness executing the same SQL statements against actual SQLite files (including persistence across reopen and two connections competing for one shot). The Worker HTTP entrypoint deliberately returns **404** for every request; no Cloudflare scripts, bindings, paid services, secrets or permissions are created by these files.

## New offline authenticated gateway prototype

`signed-gateway-candidate.mjs` and `worker-gateway-candidate.mjs` are **candidate source files only**; the default `worker.mjs` remains a 404-only entrypoint. Tests use a hard-coded **fake test key** and verify real WebCrypto HMAC-SHA256 over the HTTP method, exact path, UTC timestamp and literal request body. Clock skew, invalid owners, altered signatures, unauthorized operations and server-side missing bindings all fail closed. Only `begin`, `reserve`, `record-fake` and `status` operations are routed, through **one fixed shared-legacy-journal Durable Object key** (the old scene-keyed routing was unsafe across scenes sharing one historical Drive journal). No route generates art.

There is **no production HMAC key** and we intentionally did not create one or add a GitHub Actions secret. No authenticated gateway has been deployed. Production rollout would require separate owner confirmation, a scope-limited secret provisioning procedure, and confirmation of Cloudflare Free hard limits and safe quotas. With the current connector, account subscriptions were not readable (HTTP 403), and no Durable Object namespace existed when checked. Therefore no deployment may be considered zero-cost verified yet.

## Boundaries and meaning

- Source: `scene-reservation-core.mjs` exports `createSceneReservationClass(DurableObjectBase)`. `worker.mjs` supplies the Cloudflare base. `scene-reservation.test.mjs` executes the actual SQL with `node:sqlite`. All CI uses no secrets and calls no image endpoint.
- An immutable scene-scoped admission checked by existing `tools/scene_m3_ticket.py` is stored once; source SHA, request ID, baseline legacy journal SHA/count, shot order, shot spec SHA, and hard total attempt ceiling are fixed. No second ticket may take the scene slot. The candidate gateway routes all scene IDs into **one Durable Object for the shared legacy journal**, not one per scene. Its current SQLite singleton admits **only one scene ticket total**, deliberately rejecting a different scene with HTTP 409 even when the six-attempt baseline matches; a genuine multi-scene journal requires a separately designed versioned migration and reconciliation. This is safe fail-closed behavior, **not** a complete multi-scene scheduler or proof of a hosted lock.
- A shot reservation is a single SQLite transaction, before any possible future POST. A crash retains `SUBMISSION_UNCERTAIN_NO_RETRY`, and the next shot cannot begin until an exact deterministic **offline fake** receipt has been recorded. Never retry an ambiguous external image submission. Record fake receipts strictly; no accepted-image claim.
- This is **not yet an operational distributed lock** in the user's account: there has been no deployment, Worker binding, owner HMAC/API access, read-only authentication proof, or trusted copy of the six historical attempts. The existing Drive replacement still lacks verified CAS. Do not confuse tests of actual SQLite with tests of Cloudflare's hosted runtime.
- To connect a future production runner, build a **separately reviewed owner-gated authenticated Worker endpoint**, verify the account is Free with no overage, confirm permissible Workers/DO quotas and allowed secret scope, bootstrap the authoritative history with exact hash while all competing producers are disabled, route every legacy-journal writer through the same global coordinator (not scene-specific objects), and test crash/restart/race against a hosted but zero-inference staging instance. Explicit approval required for deployment/provisioning or any live image attempt. Only then consider a real Cloudflare image POST; preserve OPN02/OPN03 as unapproved candidates.
- Until those steps, `generation-safety.json` stays closed and `worker.mjs` has no external API. The 15-second M2 MP4 is a technical fixture, not a finished scene.

## Verify without secrets

```
node --test infra/m3-coordinator/scene-reservation.test.mjs
```

Official documentation checked: [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/), [SQLite storage API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/), [Free plan quotas](https://developers.cloudflare.com/durable-objects/platform/pricing/).

**This work should advance, not replace, the ordinary ChatGPT → owner Issue #54 → GitHub Actions control path and its mandatory scene QA.**


## Offline six-attempt history migration/reconciliation test seam (NOT deployed)

`legacy-history-reconcile.mjs` is a **disconnected offline prototype**, exercised by `legacy-history-reconcile.test.mjs` with real SQLite. It stores the complete six-attempt legacy JSON and each exact historical attempt as an immutable prefix in the same SQLite database as the candidate scene scope. It checks the separately read source against the admission's hash/count, disallows changed equal-length baselines and overwrites, and tests competing writers, interrupted transactions, crash/restart, receipt uncertainty and no-retry. Both OPN02/OPN03 remain unaccepted fixture candidates.

**Security boundary:** the test's injected `readPrivateHistory` is NOT an authenticated Drive reader; a claimed SHA alone does not establish authoritative provenance. The migration record explicitly says `OFFLINE_FIXTURE_NO_REMOTE_PROOF`, and reconciliation returns `OFFLINE_PREFIX_MATCH_NO_REMOTE_CAS`, **never** a live permit. Current offline `beginOffline` / `reserveOffline` APIs remain intentionally unchanged; this migration prototype is not yet a mandatory hosted pre-reservation gate. The current single-scene global DO admission from PR #99 also remains unchanged. No multi-scene admission, Cloudflare deployment, provider POST, Drive write, secret, permission, or spend is introduced.

**Next safe milestone:** connect an independently authenticated read-only snapshot source to this contract in a staging-only adapter, prove all legacy writers are barred or coordinated, then design a server-atomic versioned global ledger and reconciliation for evolving histories. Do not use this prototype or successful CI to justify deployment or new image generation.
