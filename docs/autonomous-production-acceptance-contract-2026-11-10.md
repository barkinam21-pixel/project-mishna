# Autonomous production is the product — not ChatGPT hand-made images

Owner correction, 2026-11-10: **The goal is an independent, repeatable production system.** A ChatGPT-generated image, even a good one, is a *visual benchmark only*. It is not evidence of a functioning autonomous generator.

## Acceptance criteria for a real autonomous OPN02 proof
1. A repository-controlled runner reads the shot specification and the approved reference manifests; no ChatGPT image-generation tool is involved.
2. A supported external model is invoked by the runner using scoped secrets, not pasted by the owner. A real reference-conditioned call must be proven in the provider request log; prose prompt descriptions are insufficient.
3. All input media stay private. Rights, provider retention/privacy, upload authorization and licensing are reviewed before any transfer. Reference source SHA-256s are verified locally.
4. Run a single GPU/model canary only under explicit approval and a verified provider-side hard spending limit. Estimated costs or a Python budget gate are **not** billing limits.
5. Save the native output, model ID/version, request parameters, runtime logs, reference hashes, exact provider usage/cost where available and SHA-256 of the output to owner-private storage.
6. Run deterministic preflight and visual parity review; fail closed on missing refs, unverified rights, composition drift or unknown billing. No auto-approval.
7. A second run from the same manifest can be launched without this chat and without manual copying of prompts. Reproducibility means traceable inputs and outputs, not necessarily bitwise identical generative pixels.
8. Only after a successful independent canary can scene-pack generation be scaled and linked to the existing automated assembly in PR #43.

## Current evidence (do not overclaim)
- Modal authentication check passed according to owner's GitHub run; **no verified Modal GPU image generation**.
- PR #46 offline layout and budget tests passed in CI; **no model execution**.
- Latest visually promising OPN02 image was produced by ChatGPT, uploaded owner-only to Drive and is **NOT a pipeline-generated asset**.
- Existing private reference pack has 8 verified images (2 primary + 6 active guides); 19 context/hold references are intentionally outside the package.
- FLUX.3 availability, GPU compatibility, license, image-reference conditioning, and hard billing cap are still unverified. FLUX.2 Klein 4B was previously invoked via Cloudflare but did not meet visual acceptance.
- No further manual ChatGPT image generation should be used as a substitute for system integration.

## Next implementation task
Integrate a provider adapter into the existing scene-pack generator with a **mock/dry-run backend first**, validating exact reference media hashes, approved conditioning input selection, no provider upload on dry-run, usage ledger, output provenance and accepted-only cache. Then test a real, one-shot provider call only after privacy/licensing/billing gates. Avoid a parallel rewrite of PR #43.
