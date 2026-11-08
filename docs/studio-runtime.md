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
