# ComfyUI image engine — 2026-11-07

## Implemented and tested without GPU

`tools/comfy_scene_images.py` consumes `episodes/berakhot-01-01/comfy-opening-images.json` and builds native Klein 4B ComfyUI API graphs: text encoder, model/VAE, four-step Euler sampling, and reference latents for each style/character reference. Graph topology follows the official distilled reference workflow. Actual GPU execution and artistic quality are **not yet verified**.

The same `ComfyClient` uses a loopback endpoint or a private HTTPS endpoint. Optional bearer auth comes from `COMFY_API_TOKEN`; tokens are not stored in manifests or reports. Redirects and credential-bearing URLs are rejected. No provisioning, model download, fal.ai, paid fallback or installation on Bar's computer occurs.

Production state is stored atomically in a private directory: full spec/workflow, model/component hashes, seed, prompt ID, image SHA-256 and review status. A queue timeout resumes the existing ID; an uncertain submission stops instead of submitting again. Concurrent runs are blocked. A stale lock after process termination requires inspection, not blind retry.

Candidate images are preserved for review and reused as pending candidates, **not accepted cache hits**. Explicit `accept(root, out, key, reviewer, continuity=True, rights=True)` records a named human review after image inspection. Only accepted, hash-matching entries are handed to the existing renderer. Changing one shot's prompt affects only that shot's key; changing shared wardrobe/reference/model settings affects dependent shots. Caption or narration changes do not invalidate images. Exact duplicate originals across specs are rejected. There is no automated proof of facial identity, anatomy, age, historical accuracy or subtle visual continuity.

The local HTTP test server uses original solid-color PNG fixtures. It exercises actual upload, queue, history and image-download requests, candidate reuse, acceptance, accepted cache hits, timeout recovery, corruption rejection and renderer-manifest attachment. It is not a model or an artistic image generator.

## Commands (operator/automation, not tasks for Bar)

Offline planning, no endpoint required:

```sh
python -m tools.comfy_scene_images episodes/berakhot-01-01/comfy-opening-images.json
```

After authorized zero-cost compute, model components and references are configured and verified:

```sh
python -m tools.comfy_scene_images episodes/berakhot-01-01/comfy-opening-images.json \
  --endpoint http://127.0.0.1:8188 --shot OPN02 --generate \
  --renderer-config episodes/berakhot-01-01/introduction-proof.json \
  --renderer-out private-media/introduction/renderer-with-images.json
```

Submission authorization and component-license/zero-cost verification default to **false**. Each generated shot must also appear in `approved_shot_ids` (empty by default); approving one style test does not authorize the other six. `--shot OPN02` isolates the style test. One submission maximum per invocation is the example default. Additional ungenerated shots stop at that limit; a new authorized invocation can reuse completed results. This is not provider-enforced billing protection: use only an independently verified zero-cost server, never infer price from a manifest flag. Runtime checks confirm node names and installed loader choices; component hashes are deployment attestations, not a remote cryptographic measurement of GPU memory.

`--renderer-out` creates a new manifest; it does not overwrite the production manifest, modify Alnilam, promote scene-level approvals, synthesize missing narration or invoke the video renderer. Existing `tools.introduction_proof`/`tools.introduction_render` remain the assembly gate. Generation stores PNG originals privately; the existing assembly cache handles normalized derivatives and final video.

The existing `introduction-proof.yml` now runs the CPU HTTP integration tests and seven-shot dry-run on push/manual dispatch. It uploads reports only, no references/candidate images or secrets. It does not attempt GPU generation. A configured server can run the CLI outside Codex; unattended real deployment is not established yet.

## Model, hardware and lawful compute

[FLUX.2 Klein 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) and its [Apache 2.0 licence](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md) were fetched. The publisher states native multi-reference support and roughly **13GB VRAM**. This is a publisher claim, not our measured peak. Reference count/resolution, precision and offload affect memory; exact host RAM/disk needs must be measured on the deployed stack. Preserve model notices; model licensing does not establish rights to references, portraits, architecture or output exclusivity.

[Official ComfyUI workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_flux2_klein_image_edit_4b_distilled.json) lists model, Qwen text encoder and VAE dependencies. Our compiler uses that native node topology; the exact deployed component revisions, hashes and individual licences must be recorded before generation. The 9B/noncommercial variants are not substituted. No weights were downloaded.

Local deployment needs compatible ComfyUI/PyTorch/drivers, sufficient GPU memory, pinned weights and a private writable asset directory. No local hardware has been assumed or installed. Cloud deployment needs the same stack, private storage/authenticated endpoint and verified zero-cost compute. GitHub's present CPU job is an orchestrator/test runner, not a free GPU allocation.

The current managed environment reports no GPU capability, no provider bindings, no `nvidia-smi` and no NVIDIA device files. [Colab FAQ](https://research.google.com/colaboratory/faq.html) explicitly restricts remote-control/web-UI bypass on free managed runtimes and does not guarantee GPU resources; it is not used as an unattended ComfyUI server. Previously quota-blocked public demos were not retried. **No available, authorized free automatic GPU server has been established.** Evidence receipts: `docs/evidence/comfy-image-backend-2026-11-07.json`.

## Precise remaining gates for seven real images

1. Authorized zero-cost GPU server with pinned compatible ComfyUI and model components; actual GPU graph test and peak memory measurement.
2. Durable, licensed approved combined style image and character sheets. The conversation-only `/mnt/data/...` image is not accessible here; no imaginary URL/hash is substituted.
3. Human approval of continuity/blocking and first generated style candidate before authorizing the remaining six. The example seven-shot manifest is planning only and keeps generation disabled. It follows the latest combined sunset/village direction, not the earlier dawn/wilderness prompt.
4. Actual inspection of identity, costume, hands, eyelines and lighting. Seeds and hashes do not prove visual consistency.

Alnilam's accepted continuity baseline, all existing release gates and PR43 remain unchanged. Zero real image generations and zero new charges were initiated.


## Live GPU/access investigation — 2026-11-07 follow-up

Evidence: [actual HTTP/hardware observations](evidence/comfy-gpu-live-readiness-2026-11-07.json). No inference request was submitted; no model executed, no image produced, no measured GPU time/VRAM. Do not confuse a RUNNING demo with allocation for this task.

| Route | Verified fact | Why not an operational ComfyUI GPU here |
|---|---|---|
| Current executor | No NVIDIA devices/nvidia-smi/provider bindings; cgroup RAM limit16GiB, CPU quota4 cores | No GPU. Installing ComfyUI or tens of GB of weights cannot create one; CPU-only Klein execution not attempted or benchmarked. |
| Official BFL Klein4B ZeroGPU demo | Live metadata RUNNING / zero-a10g; config and public `/infer` API returned HTTP200; source loads Klein4B/distilled | It runs Diffusers, not a shell/server where we can install ComfyUI. It can be a future limited fallback, not a proven permanent worker. No GPU allocation requested because the approved reference/rights gate remains unsatisfied. |
| Own Hugging Face ZeroGPU Space | Current official docs allow qualifying free personal accounts (verified, over30days) to host up to2 Spaces; anonymous demo usage2min/day, free accounts5min/day | No authorized HF account binding available to create/deploy a worker. This is not a claim that Bar has no account. Eligibility, quota and storage must be checked on an authorized account; no signup/subscription initiated. |
| Kaggle | Official CLI supports `kernels push` with accelerator selection | No authorized Kaggle connection available here; cannot verify account GPU quota, schedule a notebook or attach persistent datasets. No account created. |
| GitHub GPU runners | GPU is a larger-runner offering, not GPU supplied by our existing ubuntu-latest job | No verified zero-cost GPU runner attached; no billing-enabled provisioning. |
| Existing local/donated GPU | Can host our existing ComfyUI CLI and persistent private files without per-image API fees | None is connected with permission. No software installed on Bar's machine. Hardware/electricity/storage are not automatically free. |

Weak-GPU options were checked against current ComfyUI CLI: `--cpu-vae`, `--novram`, `--cpu`; `--lowvram` now explicitly does nothing when dynamic VRAM is enabled. Offloading can move memory pressure to RAM and increase latency; it does not guarantee Klein will fit a particular GPU or this16GiB CPU container. No4GB/8GB success is claimed. SDXL's completed trials were not repeated, and no unverified quantized model/licence was substituted.

Reference discovery covered accessible attachments, image entries in their ZIPs, known local filename and connected Drive searches. Inspected SP01 images show earlier interiors/landscapes, not the approved two-traveler combined frame. No match in these searches is not proof that the image is absent from all private storage. ChatGPT Library is not exposed as a file source here. No unrelated image was silently relabeled as the approved reference or uploaded.

Practical next step: recover the original combined reference and bind an eligible existing free HF account or an already-owned/authorized GPU. The official demo is a possible quota-limited fallback once the reference gate is satisfied; it is not a guarantee of unattended long-term ComfyUI hosting. No recurring automatic generation has been deployed.

New operator commands (not manual tasks for Bar):

```sh
# Read-only real endpoint/hardware diagnosis; exit2 means blocked, never a generation call.
python -m tools.comfy_runtime --out build/comfy-runtime.json
python -m tools.comfy_runtime --endpoint https://AUTHORIZED-COMFY-HOST --out build/comfy-runtime.json
# Copy an accessible original image privately, preserve its exact bytes/hash and keep approval false.
python -m tools.comfy_runtime --reference /AUTHORIZED/PATH/original.png
```

Reference intake does not edit an image, overwrite existing rights evidence, approve faces or update production manifests. Permission can be recorded only with explicit synthesis-rights confirmation plus provenance. Existing receipts require separate review to change. No image reference was ingested during this session because the actual approved source was not found.

Live protocol check: pointing the existing ComfyUI client at the official demo failed on `/system_stats` with JSONDecodeError (non-Comfy response); exit2 and no submission. This confirms that a live public Gradio API is not a drop-in ComfyUI endpoint. [Space storage documentation](https://huggingface.co/docs/hub/spaces-storage) distinguishes ephemeral free disk from persistent storage: do not assume model caches or results survive rebuild/restart. Keep originals and receipts in our private store; paid persistent-storage upgrades were not enabled.

Verification for this follow-up: 348 local tests passed; the real runtime probe and public-demo ComfyUI protocol check both correctly returned blocked/exit2. These do not establish GPU inference or image quality.
