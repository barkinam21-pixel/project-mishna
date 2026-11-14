# M3 reliability hardening — shared Actions queue + atomic-transport test protocol

Status: **code + mock tests only**. No image creation, cloud request, Drive write or cost.

## Confirmed risk and mitigation

1. The *existing proven* production owner workflow `.github/workflows/chat-readonly-command.yml` previously had `cancel-in-progress: false` with GitHub's **default single pending run**, which could silently replace a waiting owner request. We added `queue: max` under the same global group `mishnah-chat-readonly-command`, preserving the old one-shot code, reviewer lock and permissions. See [GitHub concurrency docs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency). Queue supports up to 100 pending runs; beyond that, events can be canceled, so a queue alone is not a durable dispatch ledger.
2. The immutable reviewed runtime's `Drive.replace` uses unconditional `PATCH .../upload/drive/v3/files/{id}?uploadType=media` followed by a SHA-256 readback. It **does not implement a server-enforced atomic compare-and-swap**; a read-before-write is NOT an atomic lock. The official [Drive v3 files.update reference](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update) does not establish a suitable If-Match media-update contract. Never label version-check + readback as distributed mutual exclusion.
3. New `tools/scene_m3_remote.py` provides a **mock-only** versioned conditional-write protocol with strict admission scope, inherited 6+ historical attempts, batch reservation and per-shot pre-submission journal records. Its `AtomicMemoryJournal` is a thread-safe test double, not Drive. `NoCASDriveAdapter` **fails closed** immediately; there is no live submission path. A real adapter must prove cross-run atomicity before use.
4. The controller refuses a second batch while another is unfinished; stores immutable prior attempt prefix; rejects conflicting owner ticket, unknown or re-ordered shots, changed spec/cap, forged receipt, foreign appended attempt, and crashed ambiguous reservation. Resuming a `RESERVED_UNCERTAIN` record never resubmits; subsequent shots are held for review.
5. New `tests/test_scene_m3_workflow_guard.py` protects queue/owner guards/secret placement, and `tests/test_scene_m3_remote.py` exercises CAS conflict, two simultaneous batch-starts, legacy journal preservation, no-CAS blocking, receipt tampering, crash/replay and mock two-shot completion. CI executes these alongside existing M1/M3 regressions.

## Integration boundary / next coding steps
- Route ALL future real M3 production jobs through the **same global serialized group** as the proven Issue54 workflow, rather than a ref-specific group; use `queue: max` and `cancel-in-progress: false` only. Never introduce a parallel producer while the legacy one-shot flow still exists.
- Source a **genuinely atomic remote coordinator** (or a reviewed single-writer architecture that provably excludes every competing writer), before converting the mock reservation into a Cloudflare POST. Drive is a backup/media journal, not a trusted CAS mutex without further provider evidence.
- At real dispatch: revalidate fresh owner-scoped scene ticket, script/source/art continuity, privacy/license/Free hard-stop/remaining quota, pinned runtime, private journal, and **write/read back reservation before each POST**, without retry after uncertain outcome. Preserve all original historical attempts and candidate hashes.
- Correct the independent artistic blockers (dawn vs sunset, narration/dialogue version, OPN/EP shot mapping) before any real scene attempt; do not let these infrastructure tests approve the screenplay or visuals.
- Treat the 15-second M2 synthetic fixture and every M3 fake receipt as NOT real cinema.

## Official sources checked (14 Nov 2026)
- GitHub Actions [concurrency guidance](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
- Google Drive [files.update v3 reference](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update).
- GitHub [git references update with non-force fast-forward](https://docs.github.com/en/rest/git/refs) as a *potential* alternate atomic coordinator; NOT implemented here, because production workflow currently has only `contents: read`, and expanding write permissions was not authorized.

**No automatic live generation; zero paid activity in this PR.**
