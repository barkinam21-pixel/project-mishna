> **Primary detailed standard:** [Animation & Directing Bible v1](animation-direction-bible-v1-2026-11-01.md). Use this for production choices. See also [shot-by-shot animatic plan](../episodes/berakhot-01-01/shot-directing-animatic-v1.md) and [offline fractional camera renderer](../tools/private_subpixel_camera_v2.py). The older `tools/private_motion_shot.py` zoompan preview is a legacy experiment; prefer the new renderer for future tests.

# Mishnah Cinema — visual and camera-motion direction (2026-11-01)

Status: USER-APPROVED DIRECTION, NOT final sign-off on every asset.

## Camera motion — binding project-wide quality rule
- Reference: private SH09 stable-motion V4 preview, which user explicitly praised as "very good".
- No visible jitter, shake, vibration, stutter, pixel stepping or unstable zoom at any point in the series.
- Use smooth, stable, cinematic camera motion, with no artificial handheld shake.
- Motion pace: **V10 is the current provisional preferred reference** (after sequential V5–V10 speed increases). This is **fully adjustable** per shot or after review, not permanently locked. Preserve the approved smooth motion path; adjust timing only until further review.
- Validate motion visually on mobile as well as by checking frame rate and full video decode. Encoding statistics alone do NOT prove absence of jitter.
- If a motion method visibly jitters, reject the method, not merely its numeric settings. Do not publish a vibrating shot.

## Visual look — binding project-wide art direction
- Mature, painterly, cinematic ancient-world illustration.
- **Slightly more faded/desaturated** than the existing SH09 preview, only a subtle change.
- **Slightly more dramatic** depth and lighting, but not overly dark, grey, cold, or harsh.
- Preserve warm practical light and natural skin tones; do not exaggerate contrast or saturation.
- Keep a consistent visual bible and continuity across scenes; treat SH09 as a style candidate, not a source-verified historical scene.

## Approvals and limits
- User approved V4 motion character, then iteratively requested faster V5–V10; on 2026-11-01 agreed to **try V10 provisionally** and explicitly requested the ability to change it later. Visual look direction is approved in principle but final color grade remains subject to visual confirmation.
- No new paid image/video API calls without separate authorization.
- Keep SH09 image and derived video private. Do not commit private assets to GitHub.
- Separate visual style approval from Mishnah source accuracy, historical QA, narration and release approval.

## New private style test (2026-11-01)
- A new original S01/SH01 setting illustration was generated as a **private style candidate** (not accepted as historically accurate or final).
- Original SHA256: `480b6d2e506d22b6c70564cf90d02a6bef4a523283c375160234c4c6926b568a`.
- A softly graded candidate and a six-second, 144-frame **constant 24fps** camera test were rendered. Video SHA256: `c281ee7308843a070f1b2ca517d2bd2b74cffd978ba9b5de238a4b70a2b74a2a`.
- Private ChatGPT Library folder: `/Mishnah Project/private-animation-style-2026-11-01`. Never commit visuals to public GitHub.
- Secondary generated infographic was **rejected** due to unreliable AI-written Hebrew and anachronistic/unsupported imagery. Do not treat it as approved reference.
- **No paid external API calls this session. ChatGPT image generation did take place; plan/usage meter unavailable.**
