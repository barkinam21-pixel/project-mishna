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
