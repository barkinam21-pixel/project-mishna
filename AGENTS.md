# Codex and agent instructions — Mishnah Film Studio

Read this file before changing the repository. The owner prefers **cloud-first, low-click** operation due to pain. Do not ask them to install local tools, copy logs, manage timelines, or repeatedly approve intermediate steps.

## Mission and stage
- A Hebrew, serious, warm, historically careful cinematic illustrated Mishnah series, starting **Mishnah Berakhot 1:1**. Distinguish Mishnah text, named commentaries, modern explanation, historical reconstruction and explicitly labeled `המחזה`.
- **Current source approval gate is not complete.** The existing 75-second pilot and 13.5-minute scripts are exploratory drafts, NOT signed-off production masters. Never turn a draft into approved scripture, narration or a published episode merely because tests pass.
- Authoritative state: `episodes/berakhot-01-01/manifest.json`, `episodes/berakhot-01-01/source-dossier.md`, `docs/operator-decisions.md`, and `docs/session-handoff.md`. Update a decision record only with evidence; do not fabricate approvals.
- Variant `חייבין אתם לקרות` versus `מותרין אתם לקרות` remains material. Mechon Mamre segments differently. Source rights and human Torah review remain unresolved. Do not silently select a reading or reuse protected manuscript images.

## Working rules
1. **Default to safe, scoped engineering.** Work in a branch or task where possible, minimize touching unrelated files, and test every changed behavior. Use PR review for multi-file invasive changes.
2. **No charges, purchases, secret creation, publication, automatic upload, or release** without explicit user approval. External spend allowance is **US$0**. Plan usage/quotas that cannot be measured are `unknown`, never `0`.
3. **Do not use TinyFish** for any task in this project. Do not call ChatGPT image generation for Mishnah: the user explicitly prefers an external free-GPU pipeline and preserving their ChatGPT image allotment.
4. **Do not assume GitHub Actions provides an AI video GPU.** FFmpeg/caption tests are allowed; generative models need separate access, measured cost, licensing and approval.
5. Audio: 24fps and 48kHz = exactly 2,000 audio samples/frame; keep integer timing. Synthetic sine pulses and colored test frames are **not proof of real Hebrew voices, lip sync or cinematic quality**. Original recordings require actual listening and pronunciation review.
6. Visuals: maintain source-to-scene mapping, character continuity, historically defensible design, and normally 4–7 distinct original illustrations per dramatic scene. A crop or push-in is not a new illustration.
7. Preserve separate replaceable voice, caption, ambience, image and edit stems. Captions must be valid Hebrew RTL, with generated SRT/VTT/ASS and readable phone-safe contact sheets.
8. Stop at approval gates. Public release requires human Torah review, voice approval, continuity review, rights checks, and a real final-video four-pass QA.

## When to use Codex
Use Codex **only for specific multi-file coding/engineering work**: manifest-driven renderer; FFmpeg/voice/asset integration; nontrivial CI regressions; data-driven test coverage; GPU notebook hardening after approval. It is NOT needed to decide a Torah variant, approve voices, generate images without authorization, or replace human cinematic review. Prefer the user's GitHub-connected workflow rather than invoking Codex needlessly or exhausting its quota.

## Verification requirements
- First inspect the manifest, source dossier, active stage and existing tests.
- For changed Python: run `python -m unittest discover -s tests -v` and the relevant preflight scripts. Run FFmpeg tests where the environment supports it. Never conflate skipped/not-run with passed.
- Cite the exact file/CI run and distinguish **tests passed** from **source verified**, **recording listened**, **visuals viewed**, **film watched** and **release approved**.
- If an official asset/recording is missing, report `MISSING` or `BLOCKED_AS_DESIGNED`, never fake an approved sample or green release.
- After each working session return five brief Hebrew items: **what changed; what was actually verified; what remains/next; whether Codex or another service is needed and why; whether Bar must do anything.** If no user action is required, say so clearly.
- Keep a durable handoff record in `docs/session-handoff.md` whenever substantial decisions or status change. Do not claim autonomous future monitoring solely because a workflow exists.
