# OPN02 Cloudflare Free plan — owner attestation and privacy check (2026-11-11)

**Owner's current report:** "בדקתי ב-Cloudflare ומופיע Free. תמשיך בהכנת ניסיון OPN02 אחד, בכפוף לבדיקות הפרטיות." The owner expressly permits preparation of **one** OPN02 candidate, subject to privacy checks. Total additional external spending remains **at most USD $1**, not $1 per request. This is an owner attestation of the plan label, **not** API proof of billing status or current free-neuron usage.

**Independent read-only checks completed via connected Cloudflare account:**
- Account authentication succeeded, and the account's model search returned `@cf/black-forest-labs/flux-2-klein-4b`; the input schema supports multipart reference images.
- Official model docs identify the Cloudflare-hosted BFL model as **zero data retention**, **partner**. Source: https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- Official 2026 model documentation confirms support for 1–4 input images named `input_image_0` etc., with each under 512×512. Source: https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
- Billing/credits/usage/subscription API endpoints returned **403** to the ChatGPT Cloudflare connector. This does not contradict the owner's observed Free label, but prevents independently verifying current plan, spend cap, and remaining neurons.
- Private Drive source archive and prior rejected OPN02 candidate still exist. **Do not publish, share, or upload the originals publicly.** Private source hash verification remains mandatory before any provider request.
- The BFL partner terms were not independently cleared for the proposed private character reference transfer. The provider's zero-retention label alone does **not** prove all upstream licensing/privacy requirements. Thus `partner_private_reference_terms_verified` and `private_direct_api_verified` must remain false until evidenced.

**Safety hardening in this branch:** `tools/cloudflare_image_backend.py` now rechecks its already-existing safety/usage gates immediately before the only billable POST; it marks the request attempted **before** transport, preventing a second submission after an uncertain network failure. Offline tests simulate one successful POST, changed usage, failures, missing references, and unauthorized calls.

**Outcome:** preparation only. **0** new Cloudflare inference requests, **0** generated images, **0** known new external charges. Unknown current account usage remains **unknown**, not zero. Do not claim image completion. Existing manifest `generation_approved=false`, `zero_cost_compute_verified=false`, and partner/private-reference gates remain unchanged. An owner attestation must never silently flip independent verification flags.

**Next actual image step:** secure an authorized private original-reference runtime, verify BFL partner terms and current usage headroom, then execute **one** OPN02 via the existing Cloudflare adapter; save the output privately and label as unapproved candidate for review. No automatic retry.
