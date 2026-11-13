# Existing Cloudflare studio through private GitHub Actions

This is a thin entry point around the current `Studio`, reference intake, candidate cache, approval gates and `CloudflareClient`, not a new renderer or image service. It does not provision a Worker, GPU, subscription or public bucket. It builds on PR52/51; both remain unmerged.

## Verified versus pending

Independent Drive restore is now verified by [owner-dispatched run43337618166](https://github.com/barkinam21-pixel/project-mishna/actions/runs/43337618166), checking fixed PR53 commit2a7544d. It returned DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED, two conditioning inputs, zero remote writes and zero inference. Owner reports the existing OAuth app is In production and drive.file only; no new consent/setup is requested. PR55/56 are merged; PR53 is not. New hardening code is tested separately and has not been dispatched with live credentials. See [current preparation audit](opn02-runtime-preparation.md).

The workflow is manual, owner-only and requires its exact commit SHA to match `MISHNAH_IMAGE_REVIEWED_SHA` repository variable. PR jobs run tests only and receive no image/Drive secrets. Repository contents permission is read-only; checkout does not retain credentials; no artifact/cache upload contains private media. The default operation is `check`. Workflow availability on the Actions page depends on GitHub accepting the reviewed workflow on the default branch; no merge is performed here.

## Existing configuration reference — already configured; do not repeat

Existing authorized credentials only; no new subscription or account is created. Configure on GitHub, never in chat:

- [Repository Actions secrets](https://github.com/barkinam21-pixel/project-mishna/settings/secrets/actions): `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (existing scoped Workers AI access).
- `MISHNAH_DRIVE_OAUTH_JSON`: existing authorized Google OAuth client's `client_id`, `client_secret`, `refresh_token`, with access to the three selected existing owner-private files. Refresh uses Google OAuth only; no token is logged or written to snapshots. The Work connector's credentials are not available to copy. If no independently authorized application exists, owner setup is genuinely required; this implementation does not create it or claim it exists.
- `MISHNAH_REFERENCE_FILE_ID`: the existing exact two-original reference ZIP. Known prior private backup ID: `1Enbrzl3h2iCybflc_c4y_-b6vmecgwfb`. Existing intake checks canonical master/board hashes. Do not substitute the differently structured curated ZIP.
- `MISHNAH_STATE_FILE_ID`: the existing owner-only JSON file. It holds the authoritative non-replayable journal/attempt history. Never reset it to retry a consumed authorization.
- `MISHNAH_SNAPSHOT_FILE_ID`: existing owner-only studio snapshot ZIP produced by `studio backup`. Known prior snapshot ID: `1G4ZFbRnBuaVAABm4jSDid8Q7P7QAvIhX`. The three IDs must differ; outputs update versions of this existing private ZIP, never the original reference ZIP.
- [Actions variables](https://github.com/barkinam21-pixel/project-mishna/settings/variables/actions): `MISHNAH_IMAGE_REVIEWED_SHA` set to the exact reviewed immutable workflow/code commit. A different head remains blocked. Updating this value requires reviewing the new code. No variable/security setting was changed automatically.

An operator may bundle these setup actions; there is no verified single click that grants credentials to both services. No further source-file upload from Bar is needed. The owner must not paste credentials in chat.

## Check, run and recovery

`python -m tools.private_drive_runtime check` verifies configuration, refreshes existing OAuth, checks owner-only access to all three files, and reads the Cloudflare model catalogue. No reference bytes are downloaded or model inference requested. Authentication is not billing/privacy/rights clearance.

`run` remains blocked until the existing manifest's new-generation, zero-cost, licence and provider-private-term gates are explicitly verified. It does not reuse the old dollar approval, promote safety flags, change OPN02 directions or automatically select Modal. For authorized execution it restores source references and a hash-inventoried private snapshot, then overlays the authoritative remote journal. Before every image POST the existing engine's uncertain-state journal is saved to Drive and downloaded again to verify its hash. If storage is unavailable or write outcome uncertain, no model POST follows. The workflow serializes its own runs and never retries a failed request automatically. Operators must not concurrently run a second independent producer against the same three files; this is not a cross-host distributed lock.

After saving a candidate locally, state remains private and unapproved and a new snapshot updates the existing owner-only Drive file with readback verification. A crash after inference but before snapshot persistence may lose access to those output bytes; remote uncertain/candidate state blocks a duplicate request rather than claiming recovery of unpersisted output. This limitation is explicit; no at-most-once API guarantee is invented. The ephemeral runner deletes local private-media after completion. The original source ZIP and previous Drive versions are preserved. No plaintext media is uploaded as a public-repository artifact.

GitHub logs emit only fixed status/error codes and safe hashes; all network errors are sanitized. Drive owner-only permissions are checked before reading or updating any file. Redirects are disabled; unknown sharing blocks. No ACL is changed. `run` returns failure on missing configuration/approvals, invalid snapshot, lost private access, quota/privacy uncertainty or storage errors. No image is automatically accepted.

Current practical blockers: new-generation gates remain closed; existing OPN02 still needs smaller figures and a village rather than fortress. This round creates no image and makes no artistic success claim.

## Live read-only validation after owner supplied Cloudflare Secrets

[Actions run43223192705](https://github.com/barkinam21-pixel/project-mishna/actions/runs/43223192705) independently authenticated using repository Secrets and returned `CLOUDFLARE_READ_ACCESS_VERIFIED`. The model catalogue is accessible. Recorded usage remained unknown; no model inference was invoked, so inference permission/billing clearance is not asserted. The original check run43223001918 skipped the production job because the reviewed-SHA gate was unset; this is why read-only checks are now separate. Manual owner-only `check` does not require the production SHA variable; `run` retains it. PR events receive no credentials.

Drive check continued in the same run and reported missing OAuth and file-ID configuration. The three IDs now default to the verified owner-only metadata in `episodes/berakhot-01-01/private-storage-locators.json`; empty Secrets no longer mask these defaults. The new journal preserves four historical consumed authorizations, not a fresh empty budget. No previous media or journal was overwritten. Existing nonempty ID Secrets override defaults.

**Read-only connection setup is complete.** The former missing-OAuth blocker was resolved by owner consent and run43337618166. Keep credentials in Secrets; do not copy or recreate them. The configuration list above is recovery documentation, not a new owner task.

After OAuth setup, `check-drive` reads all three owner-only files, restores original references and the snapshot into an isolated temporary root, validates the journal and builds OPN02 conditioning/prompt hashes locally. It performs no remote writes or inference and deletes temporary files afterward. Local validation with the existing authorized chat download already confirmed both primary hashes and clean snapshot recovery; that is distinct from Actions access, which succeeded in run43337618166. A restore into an occupied workspace correctly refused overwriting different state; the clean restore passed. No production safety flag changed. New generation still requires explicit new approval, privacy/quota verification and the reviewed SHA.
