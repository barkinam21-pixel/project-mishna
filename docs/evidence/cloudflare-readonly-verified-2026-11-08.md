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
