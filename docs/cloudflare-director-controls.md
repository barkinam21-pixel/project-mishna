# Private Cloudflare shot direction

Extends the existing manifest orchestrator and candidate/approval cache. No new production system.

## Commands

From repository root:

```sh
bin/validate_shot --shot OPN02
bin/generate_shot --shot OPN02 --dry-run
bin/review_shot --shot OPN02
```

`python -m tools.shot_controls validate_shot --shot OPN02` is equivalent. Private reports/state go to ignored `private-media/director-images`. Dry-run verifies local inputs, not live authorization/model/quota. Review reads the saved report without a provider request. Candidate images remain unapproved; the existing explicit human `accept` operation and accepted-only FFmpeg bridge remain authoritative.

For a controlled edit, pass `--override path/to/private-change.json`. Example:

```json
{"composition_notes":"Wide landscape, both full bodies no more than 45% of frame height; keep A left, B right and sunset light."}
```

Allowed override fields cover composition, camera distance/angle, lens feel, continuity, prompt_text, focal action, depth, motion implication, new composition and supported generation parameters. Overrides never edit the base manifest; they alter the normalized specification and cache key. Style lock hashes the master style/characters/references, not a claimed guarantee of image identity. The board remains direction-only. OPN01–07 have director controls, but only OPN02 is authorized for generation.

## Production credentials and zero-charge gate

The standalone adapter uses `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` from a protected execution environment. No token was created, recovered from chat, copied from the connector, or added to Actions. The authenticated chat connector is not an exportable unattended credential. CI remains offline with no provider secrets or inference.

Before enabling live generation, the operator must have verified private direct synchronous inference, model/reference rights and an enforced Free-plan hard cap. Evidence must be less than 24 hours old. `free_hard_cap_verified` is deliberately **false**: the earlier OAuth connection could not read subscriptions/invoices, and delayed usage analytics do not prove no overage. No instruction is given to weaken this gate or switch billing plans. Once independently verified, existing authorization plus the fresh runtime model/usage checks permit one request. At least 1000 neurons of reserve is required. Costs remain unknown until actually observable; estimates are not invoices.

Only direct api.cloudflare.com requests are permitted; redirects and public upload URLs are rejected. References are hash-verified, decoded, reduced proportionally to below512 pixels per axis and sent as binary PNG multipart. Source bytes are retained. No AI Gateway/cache/async storage is requested. Cloudflare's documented legal/security and operational-metadata exceptions still apply; private API does not mean absolute privacy.

## Failure and QA contract

No inference POST retry is implemented: transport errors after entering submission may already have consumed usage. The persisted uncertain state blocks resubmission. At most one safe retry was permitted by the specification, not required; conservative zero retry avoids duplicate spend. Model rejection, missing permissions, stale privacy/cost evidence and malformed inputs never retry. Preparation can be rerun without inference. Error reports contain fixed codes/types, no raw HTTP bodies/headers/secrets.

Output is decoded and validated against manifest dimensions and RGB/RGBA. JPEG is permitted only for Cloudflare; native WebP only for approved adapter families. Originals are preserved with native hash. Converted PNG pixels must equal decoded source pixels; conversion does not recover lost JPEG detail. No automatic acceptance.

Deterministic QA flags low 64×36 RGB mean absolute difference to a reference (threshold18). This is a similarity warning, not proof of matching composition. People counts, adult age, identity, costume, anatomy, text, light and originality remain `NOT_EVALUATED` without a separately verified private no-charge vision evaluator. The current implementation does not claim semantic QA or native-age accuracy. Human visual review is mandatory.

## Verified outcome

OPN02 local dry-run resolves the real original hashes with no missing requirements. Live generation is blocked before network with `NO_CHARGE_HARD_CAP_UNVERIFIED`. No new image or GPU run was made in this implementation round. Existing real OPN02 stays preserved and unapproved. Fake-provider tests demonstrate JPEG provenance, PNG pixel equality and second-run candidate cache reuse; they are not GPU evidence. Alnilam and all44 narration blocks remain unchanged.
