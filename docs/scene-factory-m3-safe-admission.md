# M3 phase 1 — safe scene-level batch admission (2026-11-14)

**Implemented in this PR:** a small M3 coordination layer on top of M1 `SceneStore` with immutable scene/shot/attempt scope; ordered shot selection; per-shot durable pre-submission reservations; append-only SHA-chained journal; resume without repeating completed shots; a deliberately uncertain stop after an interrupted reservation; and executable GitHub Actions regression tests. **This is an OFFLINE MOCK ONLY phase.**

**Not implemented / not authorized:** live Cloudflare POST from M3, real batch ticket creation, provider credential/Drive modifications, owner-signed production scene approval, art/voice generation, or finished private scene. The former Issue #54 one-shot adapter remains the only proven private real-image route, and `generation-safety.json` stays CLOSED. Live M3 must integrate the pinned runtime and trusted Drive journal, verify source/privacy/Free quota freshly, and use durable remote contention-safe reservation (local file locks alone do NOT coordinate multiple Actions runners). Do not treat this code as permission to enable billing.

## How to verify at zero charge
```
python -m unittest tests.test_scene_factory tests.test_scene_m3 -v
python -m tools.scene_m3 simulate --request-id m3-prologue-test
```
The real prologue exits with code 2 and reports `BLOCKED`, including `ASSET_CONTINUITY_TIME_OF_DAY:EP-P07`, pending approvals and missing assets. No generation occurs.

Tests construct a **synthetic structural fixture** from the 15-shot draft and a fake local source/image/audio file. This is testing the coordinator, NOT approving or producing 15 real images. In simulation: `attempted=2` means two deterministic **fake** reservations/receipts; `external_inference_requests=0`. Hash changes, attempt-budget changes, shot-order swaps and changed request identities are rejected. Crash after reservation becomes `HALTED_UNCERTAIN` with no automatic resubmission.

## Next implementation gates
1. Remote atomic single-writer reservation/lease semantics over an existing trusted private journal, safe across Actions jobs and canceled runs; do not rely on local `writer.lock` between runners.
2. Validate owner-scoped, immutable scene ticket and shot-spec SHA, max inferred operations, hard cap and fresh privacy/license/quota via existing Issue54 pathway. Test with fake Drive/cloud backend and adverse network failures.
3. Integrate one real *approved* scene ticket only after the owner authorizes an explicit bounded attempt and creative/source conflicts are resolved; preserve all six historical attempts. No automatic retry of uncertain provider outcome.
4. Then independent voice/music stages and final cinematic QA; neither mock candidates nor the 15-second fixture count as finished cinema.

Owner success state is still: one ChatGPT command -> private fully assembled scene with audit, after approvals. We are not there yet.
