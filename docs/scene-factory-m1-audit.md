# M1 audit and executable boundary — Issue77

No generation, model billing, OAuth changes or public media. M1 is an offline controller, not a completed scene factory. Read the current README first; historical statements about missing OAuth/images are superseded by the proven private OPN02/OPN03 runs.

## Reuse audit

| Existing implementation | Actual role | M1 decision |
|---|---|---|
| `tools/generation_issue_runtime.py`, Issue54 workflow | Proven owner-scoped single POST, private journal and snapshot; OPN03 run43519974519 SUCCESS independently checked | Preserve closed production gate and six historical attempts; batch dispatch deferred toM3 |
| Reviewed runtime80ba155, Comfy/Cloudflare/privateDrive modules | Reference checks, one-shot/no retry, native/PNG source chains, private persistence | Do not duplicate OAuth/provider/storage code |
| `tools/private_storyreel.py:render` | Fixed16-shot/75s, deliberately silent draft cards, usable font/RTL/sidecar helpers | Preserve legacy behavior; general offline fixture integration belongs inM2 |
| `tools/private_motion_shot.py:render` | Actual6s FFmpeg camera preview; ffprobe/full decode | Reuse camera/verification approach, not pretend it supplies scene continuity |
| `tools/build_opening_motion_previs.py` | Procedural45s motion, libass and audio prototype | Source of subtitle/24fps patterns, no final illustrations |
| `tools/original_opening_audio_canary.py` | Offline authored synthesis, not Hebrew acting | No TTS/provider change; test sound must be marked synthetic |
| `tools/scene_factory.py` | New M1 validator, dependency keys, journal/checkpoint CLI | A thin scene-level control layer over existing components, no new service |

## Real editorial conflicts surfaced by the imported15-shot draft

`scene-prologue-v02.json` transcribes the existing EP-P01–15 table, durations and intent;91s/2184frames are a draft, not measured dialogue timing. Script span references only the existing literary sequence1, whose complete bytes are hash-bound. Bible is a declared design contract, not observed image measurements.

The draft uses dawn; candidate coverage OPN02→EP-P07/P14 and OPN03→EP-P09 declares sunset and remains unapproved. Validation returns `ASSET_CONTINUITY_TIME_OF_DAY`, plus prop uncertainty and approval blockers. Literary narration-first vs45s dialogue-first vs91s delayed narration remain unresolved; OPN/EP identities are not aliases; the older12-sequence episode is not silently equated to the six-act intro. Decision records require a reviewer before clearing. Recommendation: keep draft and sunset candidates separate; a deliberate sunset adaptation may conserve assets after owner/editorial review, but the code does not approve it.

## Actual APIs

`python -m tools.scene_factory plan|dry-run|status --request-id <stable-id>`.

Default manifest and Bible are versioned under existing episode directory, with explicit JSON schemas under `schemas/`. Python validation is authoritative and stricter than schema documentation. The actual production draft must return BLOCKED and zero inference. State goes under ignored private-media. One stable request/spec returns a cache hit; the same request with a different spec is rejected. Same-spec requests still revalidate current script/assets before reusing a result.

Hash-chained append-only events are authoritative; state.json is a recoverable snapshot. Journal is fsynced before snapshot replacement. Partial/corrupt journal fails closed, never truncates silently. OS writer locks release after a process crash (Linux flock/Windows locking); multiple workers on the same host cannot mutate one journal concurrently. This is not a multi-host Drive lock; global provider quota scheduling remainsM3. Checkpoint outputs must match hashes before reuse. Subtitle-only changes preserve per-shot asset keys, changing build keys. Completed-stage snapshots are not ownership/creative approvals.

Only planning and offline checkpoints are implemented. Full production lifecycle AUTHORIZED/GENERATING/TECH_QA/CREATIVE_QA/OWNER_REVIEW/ACCEPTED is a future integration, not implied by PREFLIGHT_READY. No human approval is automated. Face/finger/historical truth, pronunciation, four-pass viewing and legal judgments are not inferred by this validator; it checks declared state and locked bytes.

## Official documentation research (14Nov2026)

- GitHub concurrency documentation https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency and changelog https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/ were read. `cancel-in-progress:false` alone previously had one-pending replacement; queue:max opts into larger queues. The M1 CI uses queue:max, but no production inference is activated. Local journal recovery is still required; queue settings are not exactly-once execution.
- https://ffmpeg.org/ffprobe.html was read. Stream/frame counters plus full decode are technical checks, not successful acting/creative continuity. Encoding bit identity depends on FFmpeg/font builds; semantic timeline and per-output hashes must be reported separately.
- Cloudflare pricing/data-usage and Apache2.0 evidence already in the existing one-shot audit; M1 does not re-check quota or open an expired creation ticket. No assumption of unlimited free GPU or free TTS. No new TTS chosen, so no voice licence/quality claim.

## Acceptance and remaining work

Executable tests cover dawn/sunset, altered script/Bible, shot swaps/frame gaps, costume/prop/axis/eyeline/weather, invented source attribution, chronology70CE, unsafe captions/audio slots, duplicate requests, changed output cache, crash after journal fsync, corruption and concurrent writers. Real15-shot dry-run is BLOCKED, as required. Tests check metadata consistency; they do not prove visual sameness of actual pixels.

M2 must deliver an explicitly synthetic technical MP4/audio/captions through existing FFmpeg mechanisms in a separate dependent PR. M3+ remain provider batches, genuine Hebrew scene audio, licensed full sound design, private scene delivery and human review. No human technical action is required for M1.
