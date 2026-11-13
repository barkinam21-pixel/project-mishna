# OPN02: verified FLUX.3 Image Klein layout preflight — code-only research, no generation

Status: **CPU-validated layout draft, NOT an implemented provider adapter or approved film asset**.

## What is different from our existing FLUX.2 Klein 4B route?

FLUX.3 Image Klein released 2026-10-15 supports layout boxes and multi-reference edits. The official Black Forest Labs reference CLI accepts `--boxes` JSON records with a **0.0–1.0** coordinate scale, in **[top, left, bottom, right]** order. Its prompt-upscaler's text format may use **0–1000 integer** coordinates; these are different interfaces. Passing 0–1000 values directly as CLI boxes is a unit bug.

Official reference: https://github.com/black-forest-labs/flux-3-image-klein#bounding-boxes
Publisher details/licensing/VRAM: https://bfl.ai/blog/flux-3-image-klein

The offline plan `episodes/berakhot-01-01/opn02-flux3-layout-draft.json` gives two rear-view, full-body travelers bounded to **31%** of height, elder left / younger right, dominant landscape and genuinely distant village, with source layer labeled symbolic dramatization. The converter has no model SDK, no API or web calls, and deliberately refuses any `generation_authorized=true` or `reference_images_uploaded=true` input. It emits a CLI-compatible box list for **future** authorized use; it does not build the final model prompt or claim that the model follows boxes perfectly. A prompt-upscaler, actual reference-binding semantics and identity continuity require separate validation.

Read-only command:

```sh
python -m tools.flux3_layout_preflight episodes/berakhot-01-01/opn02-flux3-layout-draft.json
```

To write only the normalized geometry, without generating anything:

```sh
python -m tools.flux3_layout_preflight episodes/berakhot-01-01/opn02-flux3-layout-draft.json --out private-media/opn02-flux3-boxes.json
```

## Stop gates: no useless model calls

1. Verify a **private, zero-additional-charge GPU/ComfyUI** runtime compatible with the new FLUX.3 INT8 model and the required prompt upsampler (which is a separate 9B model). Published vendor claims include an 8 GB VRAM route with INT8 in ComfyUI; **our connected runner has not been measured**, and the reference CLI's B200 memory numbers are much larger. Do not claim GPU eligibility from model-card claims alone.
2. Verify the *FLUX Kommunity License*, rights to use specific private character reference images and actual service/data handling. This license differs from the existing FLUX.2 4B Apache license; do not silently swap weight packages or assume commercial permission for all uses.
3. Verify the official ComfyUI workflow actually passes layout control (not merely text) **and** the specific role and size reference inputs; no tested integration exists yet. Do not upload to a public ZeroGPU Space.
4. A **single fresh user-approved** candidate only if zero-cost, privacy and terms are proven. Check bounding-box adherence, painterly look, anatomy and costume visually. All approvals remain false until review. Never send an automatic paid fallback or repeatedly guess prompts.

The current `PR #43` code is not replaced. This experiment is additive and isolated; it does not change the existing CLI or model configuration. If no compatible free private GPU is found, stop at `BLOCKED_FREE_PRIVATE_GPU_NOT_AVAILABLE` rather than keep producing code.