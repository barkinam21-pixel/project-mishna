# Mishnah Studio — Production Architecture (2026-10-31)
Status: **tools/research prototype only**. This document is an integration plan, not a claim that generative backends already work.

## Design contract
**Goal:** create historically responsible, serious, warm illustrated Mishnah films from a reusable, evidence-backed, predominantly cloud-based pipeline. Start with Berakhot 1:1 before Gemara. Deliver a 60–90s *proof*, not a full episode, before spending on generative video. Bar's laptop should not need to run ComfyUI, render footage, or edit a timeline.

## Existing working components
- GitHub repository: source control and durable history.
- GitHub Actions: Python unit tests and **no-spend offline preflight** that outputs an artifact (`build/preflight.json`).
- `tools/studio.py`: machine-readable manifest validation and a release block.
- `episodes/berakhot-01-01/source-dossier.md`: source comparison and outstanding rights/text questions.
**Not yet integrated:** retrieval API, image model, character references, GPU backend, Hebrew TTS, animation model, scene-assembly renderer, real MP4 deliverable. Never describe these as working today.

## Recommended minimalist stack
| Stage | Preferred | Why | Hard gate |
|---|---|---|---|
| Source research | Sefaria API + checked edition URLs; Mechon Mamre as copyrighted comparison reference | stable source references, version licenses, divergent readings | 2 independent editions, variants, rights, named reviewer |
| Production manifest | Python JSON, GitHub versioning | one truth, reproducible inputs | no free-text-only storyboarding |
| Original keyframes | reference-guided FLUX.2 Klein 4B via cloud ComfyUI when rights/cost verified | character and location continuity | lock visual bible and characters first |
| Hero shots | limited image-to-video with Wan2.2 or LTX, using approved first frames | restrained cinematic motion | compare 2 clips against fixed QA rubric before choosing |
| Narration | Hebrew voice audition, offline-first; provider only after testing pronunciation | quality matters more than vendor | voice approved and dictionary checked |
| Assembly | FFmpeg on standard GitHub Actions runner (within job limits) | deterministic frame-based editing, H.264, captions | no external generation service required to render existing assets |
| Publishing | manual approved release | quality, text and rights remain human accountable | reviewer, credit, and playback test |

**Important infrastructure boundary:** Standard GitHub-hosted Actions runners are not GPU video-generation machines. GPU generation requires a *separate* GPU service/runner, with its own quotas and billing. The orchestrator can stay on GitHub, but it cannot turn the standard Actions runner into a GPU for free.

## Concurrent work without chaos
Safe independent parallel lanes **after** source lock:
- Lane A: scene composition and character continuity
- Lane B: narration/pronunciation clips
- Lane C: rights, citations and subtitle preparation
All lanes deliver versioned files associated with the same episode manifest hash. Animation is dependent on Lane A approved frames. Final assembly depends on accepted images, audio and captions. The source reviewer is independent of content generation. Never allow two agents to change approved master text or the same artifact simultaneously.

## Prototype approval boundaries
1. Source dossier (including variant decision, rights and human Torah review)
2. Literary script, then source-to-scene mapping
3. Visual bible: 1 character reference + 1 location reference; approval
4. Voice audition and pronunciation approval
5. 60–90s private proof; review: silent, audio-only, continuity, beginner comprehension
6. Repeatable episodic rendering; release only after separate authorization

## Budget and operations
- Current setting: **$0 authorized spend on external models**. No GPU/video/TTS paid service may be called by any current workflow.
- Google/third-party notebook GPU access is variable; cannot assume free on-demand capacity.
- Standard GitHub Actions for **public repositories** are generally free; this does not make generative video free. Check storage, artifact retention, and any provider costs before production.
- Meter operations: request, output, accept/reject, cache hit, external credit, external charge, workspace usage unknown.
- Planning script must work offline: render `preflight.json` and fail closed before paid services.
- Store API credentials as GitHub Actions secrets **only after explicit user authorization**; never commit secrets to a public repo. Avoid granting a workflow write tokens without need.
- Do not commit large AI renders, copyrighted texts, personal images or unreleased footage to the public repository. Use separate storage and only approved public thumbnails.

## Visual policy
- Painted cinematic semi-realism, serious, warm and accessible, not generic hyperrealism or children's cartoon.
- Dramatization visibly labeled, historical certainty never implied.
- A scene uses a planned pack of 4–7 distinct approved keyframes, not one still and repetitive zooms.
- Use at most two derived crops per source; no text printed into generated frames.
- Camera axis, props, costumes, light direction and source tag recorded per shot.

## Integration acceptance tests (before any provider is enabled)
1. Offline sample manifest validates and yields BLOCKED_AS_DESIGNED while approvals are missing.
2. Generated output (once enabled) must maintain a character's face/wardrobe and the set across at least 4 views, Hebrew subtitles must remain legible on mobile.
3. Film motion must convey a beat, with stable hands/faces and no unexplained pose drift.
4. Audio narration verified for key Hebrew/Aramaic terms; no unauthorized voice cloning.
5. Render can be repeated and changed at shot-level without regenerating every shot.
6. Cost ledger tells us billed/unknown; processing stops at cap; never retries a paid call blindly.

## Links to canonical source and tool documentation
- https://developers.sefaria.org/reference/getting-started
- https://www.sefaria.org/Mishnah_Berakhot?tab=versions
- https://github.com/Comfy-Org/ComfyUI
- https://github.com/black-forest-labs/flux2
- https://github.com/Wan-Video/Wan2.2
- https://github.com/Lightricks/LTX-2
- https://ffmpeg.org/documentation.html
- https://docs.github.com/en/actions/concepts/billing-and-usage

**Next productive action, without asking Bar for technical details:** finish and lock the source edition/variant dossier with a qualified human reviewer before writing the shooting script or generating character assets.
