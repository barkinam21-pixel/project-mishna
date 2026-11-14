# M2: offline technical assembly proof

Extends the existing `tools/private_storyreel.py` FFmpeg assembly utilities; no replacement image, voice, Drive or Cloudflare engine. Depends on M1 PR #79. No inference or paid GPU use.

## Reproduce without an agent

Requires Python, Pillow, FFmpeg/ffprobe, fontconfig and a Hebrew font (CI installs these on the runner, not Bar's computer).

```
python -m tools.scene_factory assemble --technical-fixture
python -m tools.scene_factory assemble --technical-fixture
python -m tools.scene_factory status
python -m unittest tests.test_scene_factory tests.test_scene_factory_assembly -v
```

The first invocation renders a 15-second, 960×540, 24fps H.264 MP4, 48kHz stereo AAC, embedded Hebrew mov_text subtitles, burned Hebrew captions, synthetic WAV, subtitle sidecars, contact sheet, measured ffprobe report and checksummed receipt. The second invocation verifies every cached file and avoids encoding. A corrupt cached file blocks rather than silently replacing it. An OS lock protects concurrent local renders; M1 records an assembly checkpoint and can reconstruct its snapshot from the journal. Existing Drive backup/restore and distributed job coordination are not implemented by this fixture helper.

Exactly 15 synthetic one-second slots / 360 frames and 720000 source PCM sample frames. This deliberately compressed test timeline is **not** the 91-second prologue, a 60–90s artistic proof, approved footage or narration. Tone/noise test stems are authored locally. Alnilam and all 44 narration segments remain unchanged and unused. No private reference files enter this fixture path. Actual production assembly remains explicitly blocked.

Checks include full decode, black/freeze detection, stream formats, dimensions, frame count, color metadata, subtitle language and duration, source audio RMS/peak, sample count, actual rendered motion, repeat cache reuse, corruption and unsafe-caption rejection. Source signal measurements do not prove final subjective sound quality. A decoded frame was visually inspected for Hebrew direction and the explicit test watermark; no complete human silent/audio/continuity/beginner review took place. All four remain NOT_PERFORMED in the receipt. No face, hand, age, native accent or artistic continuity claims are made.

## Artifact

Private Drive MP4 (readback: `shared=false`, sole permission owner):
https://drive.google.com/file/d/1KC_nlBUlyBI1w6N8lgrIItAReQzz_4yt/view?usp=drivesdk

See `docs/evidence/scene-factory-m2-2026-11-14.json` for exact hash, probe and test evidence. Source media and generated local state stay ignored under private-media; no private artifacts are uploaded by CI. The offline workflow runs real FFmpeg integration, then verifies two consecutive assemblies use the same cached outputs. GitHub Actions runner availability/quotas still apply.

## Still blocked for an artistic scene

M1 reports actual unapproved script/assets and unresolved dawn/sunset, voice entry, shot-ID and six-act crosswalk decisions. Real source, visual, sound and final review gates remain required. M3 scene-scoped generation authorization and provider idempotency, M4 approved narration/music integration, and M5 actual artistic proof are not delivered here. No generation permission is inferred from a successful fixture.
