# Live Cloudflare access and safe-generation gate — 2026-11-08

Scope: **read-only verification** for the existing Mishnah image pipeline and `tools/cloudflare_image_backend.py`. No model inference, no reference upload, no paid action, no approval, no PR merge.

## What was verified live using the connected Cloudflare account

1. **Authentication succeeds:** `whoami` returned an authenticated user; `GET /accounts` returned success and one accessible account. Account and user identifiers intentionally omitted from this public repository.
2. **The target model appears in this account's catalog:** `GET /accounts/{account_id}/ai/models/search?search=flux-2-klein-4b` returned the exact model identifier `@cf/black-forest-labs/flux-2-klein-4b` and image-generation/editing description.
3. **The account API exposes its request shape:** `GET /accounts/{account_id}/ai/models/schema?model=@cf/black-forest-labs/flux-2-klein-4b` succeeded. It specifies a required multipart input and an output image as base64.
4. **Billing tier remains unknown:** read-only `GET /accounts/{account_id}/subscriptions` returned HTTP 403, Cloudflare code 10000; the connector reports that account subscription reads require Billing Read/Write permission unavailable to this OAuth session. **Do not infer this account is Free from successful model discovery.**
5. **No AI usage or charge was measured.** Catalog/schema access is not proof of inference access, free quota balance, or an enforceable zero-cost hard cap.

## Official documentation checked

- [Model page](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/): the model is Cloudflare-hosted, marked zero data retention, and uses the provider's terms.
- [Platform data usage policy](https://developers.cloudflare.com/workers-ai/platform/data-usage/): ordinary stateless inference is documented as zero-data-retention for customer inputs and outputs once processing completes; third-party routed services can have separate terms. This is a provider commitment, not an observed end-to-end security audit.
- [Launch and multi-reference example](https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/): up to four binary reference images, named `input_image_0` through `input_image_3`, each **smaller than 512 x 512**; distilled four-step inference.
- [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/): published 10,000 free Neurons/day allocation; for Klein 4B, 5.37 neurons per input 512x512 tile and 26.05 per output tile. Published policy and account-specific entitlement are separate questions.
- [Free-model restrictions announced July 2026](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/): some models became Paid-only. A catalog match does not establish the chosen model's request-level tier access.

## Existing code and next gate

`tools/cloudflare_image_backend.py` already implements the authenticated multipart adapter. It deliberately requires `private_direct_api_verified`, `licenses_verified`, `free_hard_cap_verified` and non-expired evidence before submitting an image. None of these flags was promoted on account discovery alone. The branch's default scene generation authorization remains false. Continue using the existing `cloudflare` backend; do not create a redundant adapter.

**Next safely executable task:** establish the actual account tier and hard no-charge enforcement using an authorized account billing/readout surface, verify reference/model permissions, and confirm genuine quota headroom. Only then may a single existing-approved OPN02 candidate be submitted if all creative and rights gates also pass. Do not upload private references to a public Space or send any synthetic/real inference request just to test tier eligibility without explicit authorization.

## Status

`ACCOUNT_AUTHENTICATED` / `MODEL_DISCOVERABLE` / `SCHEMA_READABLE`; **`GENERATION_BLOCKED_UNVERIFIED_ACCOUNT_BILLING_AND_FREE_HARD_CAP`**. External inference calls: **0**. Private reference uploads: **0**. New approved images: **0**. No subscription or billing changes.

## Owner-confirmed account plan (subsequent conversation)

The owner explicitly confirmed that they already checked their Cloudflare account and it is **Workers Free**. Do not ask the owner to repeat this check. This is an owner attestation, not a successful Billing API read; the connector still lacks Billing Read. Cloudflare's official pricing states that Workers Free provides 10,000 Neurons/day and fails requests after its free allowance rather than charging overages. **This resolves the plan-type uncertainty at the owner-attestation level, but does not prove model-specific eligibility, current remaining allowance, or inference success.** No generation is authorized yet; require a separate explicit owner approval for the single OPN02 trial. No billing change or model inference performed.
## Read-only model eligibility follow-up — 2026-11-08

This section **adds to**, not supersedes, the historical account/catalog/schema checks above. It records new evidence without creating another status document, promoting rights/creative gates, or reproducing private media.

### Historical cross-check that avoids unnecessary re-generation

- The repository already records a successful **real** authenticated Cloudflare \`@cf/black-forest-labs/flux-2-klein-4b\` inference on 2026-11-07 in [opn02-cloudflare-real-candidate-2026-11-07.json](opn02-cloudflare-real-candidate-2026-11-07.json). A second prior successful trial on 2026-11-08 is in [opn02-private-2026-11-08.json](opn02-private-2026-11-08.json). These are historical operations, **not** requests made in this follow-up; both returned 1024×576 images, but neither is an accepted production image. [Three-candidate visual review](opn02-three-candidate-visual-review-2026-11-08.json) documents the remaining composition and style faults. The one-shot authorization was consumed, and \`generation_approved=false\` remains mandatory.
- The owner confirmed the connected account is **Workers Free**. Historical successful inference and that owner attestation are **strong evidence of practical usability**; they are not a Billing API proof of the subscription state at the exact prior request timestamp, and they do not guarantee today's request success.

### Newly checked read-only information

- An authenticated **GET** to \`/accounts/{account_id}/ai/models/search?search=flux-2-klein-4b\` succeeded with the exact model name. The returned model has task \`Text-to-Image\`, an empty \`tags\` array, and \`properties\` limited to \`partner=true\` and a link to the BFL terms. **No Free/Paid entitlement, remaining Neurons or spending-cap field is exposed in this response.** No account ID, token or private reference is recorded here.
- [Official Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) (last updated 2026-10-20) explicitly lists **Workers Free: 10,000 Neurons/day**, with no excess-charge tier (\`N/A — Upgrade to Workers Paid\`), failing further requests on limit. Reset is 00:00 UTC. This verifies the **published plan policy**, not the account's actual live remaining balance.
- [Cloudflare's 2026-07-28 Paid-only model announcement](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/) lists \`kimi-k2.6\`, \`kimi-k2.7-code\` and \`glm-5.2\` as restricted on Free; \`flux-2-klein-4b\` is **not** among the named restricted models. Absence from this announcement is supportive, **not** a per-account entitlement certificate or guarantee no newer restriction exists.
- No supported read-only **Workers AI account-specific Neurons balance / model-entitlement** endpoint was found in the exposed Cloudflare OpenAPI \`GET /accounts/{account_id}/ai/*\` surface. The previous subscriptions \`403\` is preserved as an existing known permission limit rather than repeated. AI Gateway billing counters are not a reliable substitute for direct Workers AI inference usage.

### Safe operational conclusion

\`HISTORICAL_INFERENCE_SUCCESS_VERIFIED_FROM_REPO\` / \`OWNER_ATTESTED_WORKERS_FREE\` / \`CURRENT_CATALOG_DISCOVERABLE\` / \`PUBLISHED_FREE_HARD_LIMIT_CONFIRMED\` / \`CURRENT_ACCOUNT_SPECIFIC_ENTITLEMENT_AND_USAGE_UNKNOWN\`.

This follow-up used **read-only** model discovery/documentation only; **0 new inference requests; 0 new private-reference uploads; 0 image outputs; no paid activation, payment change, PR merge, or approval-flag change**. It neither proves an invoice amount for prior trials nor clears source/privacy/licensing terms. Preserve the existing Cloudflare adapter and independent \`tools.studio\` runtime. For any future **new** OPN02 attempt, obtain fresh explicit owner authorization, verify private reference rights/provider terms and model-specific usage safety, and keep \`accepted=false\` pending visual review. Do not submit a probe image merely to test access without authorization.
