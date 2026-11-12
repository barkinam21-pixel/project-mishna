# Running the studio without Codex

The runtime imports existing Python modules directly. It calls no agent, ChatGPT, Copilot or GitHub API. It needs Python3.12+, Pillow12.0.0 and, for video, FFmpeg/FFprobe and fontconfig with a Hebrew font. Existing legacy `tools/studio.py manifest.json` behavior is preserved.

Run from the checkout (Windows/Linux):

```sh
python -m tools.studio doctor
python -m tools.studio plan
python -m tools.studio run
python -m tools.studio resume
python -m tools.studio review
python -m tools.studio proof
```

Every new command emits JSON with status, what_completed, blocked_reason, next_action, outputs and cost. Exit2 means blocked, not a silent success. CPU defaults never contact a provider. `doctor --online` checks a configured authorized endpoint without submitting a generation. No provider or fallback is automatically provisioned.

The private board is `private-media/studio/review/index.html` and its contact-sheet.png. Placeholders are visibly missing media; candidates never become accepted. A validated private `candidates.json` may map already ingested candidates to shots; future ingestion UI is not implemented. Source script/shot mapping is taken from the existing image manifest; the planner records script/map hashes, it does not interpret arbitrary prose or invent scene timing.

## Existing authorized ComfyUI environment

A deployment operator sets `COMFY_ENDPOINT`, optional `COMFY_API_TOKEN`, `COMFY_PRIVATE_ENDPOINT_VERIFIED=true` and `COMFY_ZERO_COST_VERIFIED=true` only after verifying the endpoint's privacy, usage permission and no-charge compute. These are attestations, not proof supplied by this program. Tokens remain environment-only. No such environment was provisioned during this implementation. The same manifest graph runs on another compatible ComfyUI server; model component IDs/hashes/licenses and reference/shot approval gates remain mandatory. Changing endpoint does not change asset cache keys. Queued work cannot be polled against a different server.

Ordinary operation requires no JSON edits or GitHub write access; initial endpoint/model/rights provisioning remains an operator setup step. Existing generation authorization is currently false and is never upgraded by runtime settings. This code alone cannot supply free GPU hardware or guarantee consistency of generated faces.

## Restart and recovery

The persisted queue precedes image work. The existing image engine journals uncertain submission before POST and saves the returned queue ID before polling. `resume` polls queued IDs only; it does not generate newly planned jobs. Unknown submissions block automatically. A lock left by a known dead runtime process can be removed during resume; a live/unknown owner remains blocked. Restored stale locks should not be imported. Partial HTTP results never imply accepted art.

Portable private backup and restore:

```sh
python -m tools.studio backup --archive private-media/backup-001.zip
python -m tools.studio restore --archive private-media/backup-001.zip
```

Backup requires an idle image engine, includes local private media/state and a checksum inventory, excludes existing ZIPs, runtime endpoint configuration and key/credential files. Restore requires a trusted backup, validates every member and hash before writing, rejects path escapes and conflicting local files; it never overwrites media. Keep the code checkout/commit and dependency versions separately. Approved state in a trusted backup is preserved, never created by restore. Copies of ZIP archives must be kept on existing private persistent storage by the host backup facility. Automatic Drive OAuth/mount access independent of chat has not been configured or claimed.

## Current actual gates and limitations

- No authorized private ComfyUI GPU endpoint is connected. No free compute allocation was claimed or model generation performed. Public ZeroGPU references remain forbidden; existing Cloudflare paths are not an automatic fallback.
- Repair jobs are surfaced as blocked until a verified masked/inpainting workflow is installed; no unsupported model feature is fabricated.
- The real rear-view OPN02 was restored from owner-only Drive and its exact known hash verified. It can be viewed on the private review board, but remains unapproved.
- Seven accepted distinct images, matching N01/N02 Hebrew audio, measured caption times and scene/source rights/approval gates are still required for an artistic proof. The earlier Alnilam audition is not a replacement for matching narration.
- Existing camera motion/FFmpeg checks remain the source of rendering behavior. No new transitions, complete film or artistic quality improvement is claimed in this runtime integration.
- Tests use CPU subprocesses with blocked networking and a fake local ComfyUI server, including a queued interruption and resume without another POST. A fake image or technical MP4 is never evidence of real model generation or an approved film.

## Cloudflare adapter in the same studio CLI (2026-11-08)

**Implemented, not yet a live unattended production service.** The primary `python -m tools.studio` commands now support explicitly selecting the already existing Cloudflare Workers AI adapter, without a separate system or Codex:

```sh
MISHNAH_IMAGE_BACKEND=cloudflare python -m tools.studio doctor
MISHNAH_IMAGE_BACKEND=cloudflare python -m tools.studio plan
MISHNAH_IMAGE_BACKEND=cloudflare python -m tools.studio run
```

On Windows CMD, use `set MISHNAH_IMAGE_BACKEND=cloudflare` before the `python -m tools.studio ...` command. These are **operator reference commands**, not steps the owner must perform in this session. The default without the explicit selector stays ComfyUI. The runtime never chooses Cloudflare as a silent paid or privacy fallback.

Cloudflare selection reuses the same `tools.comfy_scene_images` specifications, private state/cache, review board, existing `CloudflareClient`, and candidate-only approval flow. There is no GPU/ComfyUI requirement on that branch. Credentials, if later provisioned safely to a private runner, are `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in **protected environment variables only**; the chat connector does **not** expose reusable unattended secrets. This revision has **not** created keys, obtained reference access in that runner, changed billing, or activated generation.

**Safety:** the real image manifest has `generation_approved=false`, `zero_cost_compute_verified=false`, `component_licenses_verified=false`, and the Cloudflare backend has `free_hard_cap_verified=false`. Those gates remain deliberately closed; model discovery and the owner's Free-plan attestation do not turn them on. Missing credentials, unknown quota, unverified licenses/private reference conditions, stale hard-cap evidence and no new one-shot approval block **before image inference**. Even with all gates deliberately cleared by an authorized operator, the Cloudflare branch is limited to **one selected shot per run**, and a failed synchronous POST cannot be blindly retried by `resume`.

**Important privacy/recovery bug fixed:** Cloudflare's synchronous `submit` returns the *full image as Base64*. Before this change the generic orchestrator wrote that response wholesale into `state.json` and `usage.jsonl` as a fake queue ID. It now keeps the synchronous bytes **only in memory** until saving the native image and hash-verified PNG; logs receive only a short non-replayable identifier, and a crash leaves `SUBMISSION_UNCERTAIN` rather than consuming another request. This fix is guarded by a regression test that checks all persisted JSON/text outputs. A pre-existing legacy queue entry does not authorize replay.

**Existing remote Workers audited read-only:** the connected Cloudflare account already contains `mishnah-image-mcp`, `mishnah-image-view`, `mishnah-style-anchor`. The first has an `AI` binding, proving a Worker-bound deployment route exists without an external API token inside the Worker, but **its currently deployed script selects Klein 9B (not the verified 4B configuration)** and has publicly accessible-looking generation/MCP routes with `Access-Control-Allow-Origin: *` and no verified request-auth gate. Its source also carries inline base64 reference data. These are **security/privacy and quota-exhaustion concerns**, not evidence that a private autonomous studio is ready. **Do not connect the project, publish endpoint URLs, invoke test/generation routes, or silently repurpose this deployed Worker.** Its configuration and auth must be reviewed and hardened with owner authorization before reuse. No Worker was changed/deployed during this audit.

**Remaining operational blockers:** private persistent image/reference storage for an independent runner; safe credentials or a hardened AI-binding Worker endpoint; explicit fresh one-shot approval; model-specific rights/privacy clarity; and source/style human review. The existing R2 listing returned 403 (access/plan not confirmed). Do not infer a free R2 store or any public upload permission. See [read-only account evidence](evidence/cloudflare-readonly-verified-2026-11-08.md). No new image, service payment, deployment, voice or PR merge was made.

## Reference and image-runtime hardening (follow-up)

`python -m tools.studio restore-references --archive private-media/verified-originals.zip` restores the **existing two-image original package** through the existing intake validator. Place it on the private persistent filesystem using the host's already authorized backup facility. This command checks exact master/board hashes and sizes, preserves existing reference rights, refuses conflicting original files, never changes the public manifest and never enables generation. It needs no chat connector, new provider or GitHub write permission. The 13-entry curated library is not this two-image package; it remains archived separately, without uploading the boards to the model.

Recorded `director.reference_preparation.crops` are now enforced by the shared image engine, rather than being prompt text only. Crop source must be a hash-matched authorized reference; boxes, dimensions and derived PNG hashes must match the receipt. Dry-run computes only in-memory derivatives and stops on mismatch. Actual generation writes private hash-addressed derivatives and sends those exact inputs to the selected existing adapter. Changes to the recorded preparation already change the cache key. Encoder-version changes may cause an honest hash failure; do not silently re-label derivatives as the old bytes. ComfyUI checks required nodes/model filenames before any reference upload. Cloudflare accounts for all derivative inputs in its quota estimate and validates their count/hashes. No real generation was used to verify these changes.

Optional `private-media/studio/composition-measurements.json` supports **human observations**, not automatic person detection. A mapping for OPN02 has `image_sha256`, a named `reviewer`, `method: human_bounding_boxes`, and two `boxes` with `character: A/B` and integer pixel `xyxy`. Review rejects wrong image hashes or invalid boxes, flags heights outside25–35% or reversed left/right order, and stores a private composition report. Absence of measurements does not mean composition passed; identity/style/anatomy remain unevaluated. This supplies no native mask, spatial control or automatic approval. No new layout illustration was generated.

Backup now rejects symlinks before reading source bytes and verifies that files did not change between inventory and archive creation. Restore rejects symlink archive members. A changing file blocks the backup instead of publishing an inconsistent final ZIP. These are local/mounted-private-filesystem operations; no unattended Drive credential or remote storage service was provisioned.

The current Cloudflare gates remain closed: no fresh generation authorization, account-specific runtime headroom unknown, private partner-terms precedence unresolved. No unsupported mask/ControlNet is enabled, no retry added, and no free GPU allocation asserted.

## Hard-blocking verification outcome — 2026-11-08

The owner conditionally authorized **one** new OPN02 attempt **only** if private references and strict no-extra-charge operation are verified. This is **not** blanket permission to flip `generation_approved`, `zero_cost_compute_verified`, `component_licenses_verified` or a billing-plan flag without evidence. The prior one-shot usage record stays consumed; the new one-shot needs a separately documented authorization receipt after preflight.

Read-only connected Cloudflare API inspection confirmed Klein 4B is listed, the project Worker has an AI binding, and `/workers/account-settings` reports `default_usage_model=standard`. **None prove Workers Free.** Account billing usage/profile/subscriptions/spend-policies read requests return 403, so neither account plan nor no-overage capability is verified through this connector. The [official Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) provides a 10,000 Neurons/day hard cap **for Workers Free**, but Paid may bill beyond free usage. An AI model catalog entry is not a plan receipt.

Cloudflare [labels Klein 4B “Zero data retention”](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/) while linking to [BFL Terms](https://bfl.ai/legal/terms-of-service), whose general license text covers retaining and using inputs/outputs, and [BFL's API terms](https://bfl.ai/legal/flux-api-service-terms) discuss use of inputs for improvements. **The exact governing partner/subprocessor agreement for this Cloudflare-hosted endpoint is not proven by the connector.** Neither an unrestricted public Worker nor an anonymous file upload is acceptable for private reference images. As an added defense, `CloudflareClient.readiness` now refuses private generation without independently documented `partner_private_reference_terms_verified=true`; this flag remains unset in the actual manifest. It must never be inferred merely from the model catalog's “zero retention” badge.

**No inference/post/upload/spend in this check.** Do not deploy a Worker, create a secret, or change the account plan merely to bypass these gates. The next genuinely useful non-code action, if allowed by the owner, is permission-controlled account-plan/billing verification and a definitive partner-data-handling answer. Until then, use existing local assets only; no owner action is automatically assumed.
