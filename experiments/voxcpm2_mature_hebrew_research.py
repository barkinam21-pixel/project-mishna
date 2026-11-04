# Standalone research experiment for Mishnah narrator voice design.
# Requires: pip install voxcpm soundfile ; model weights need network access.
# NOT executed end-to-end in this environment; GPU/model currently unavailable.
# Do not use for publication until the speaker quality and all licenses are reviewed.
from pathlib import Path
import json
import numpy as np
import soundfile as sf
from voxcpm import VoxCPM

VOICE_DESC = (
    "A warm mature male voice, approximately 65 years old, a native Israeli Hebrew "
    "speaker, thoughtful and kind senior scholar, rich natural baritone with an "
    "affectionate gentle smile, calm confident delivery, nuanced emotion, precise "
    "pronunciation, and natural pacing; never theatrical, never shaky, never raspy, "
    "never a young broadcaster, and absolutely no foreign accent"
)
HEBREW_TEXT = (
    "מאחורי מילות המשנה עומד עולם רחוק. "
    "חכמים למדו, שאלו, והעבירו את המסורת מדור לדור. "
    "כעת נפתח במסכת ברכות, ונשאל שאלה פשוטה: "
    "מתי קוראים את קריאת שמע? "
    "רבן גמליאל אומר: עד שיעלה עמוד השחר. "
    "אבל מה משמעות הדברים? כדי להבין, נחזור אל ראשית הסיפור."
)
model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
wave = model.generate(text=f"({VOICE_DESC}){HEBREW_TEXT}", cfg_value=2.0,
                      inference_timesteps=10, seed=731)
wave = np.asarray(wave, dtype=np.float32).flatten()
if not np.isfinite(wave).all():
    raise ValueError("Output contains non-finite audio")
peak = float(np.max(np.abs(wave)))
if peak <= 1e-5:
    raise ValueError("No audible signal generated")
if peak >= 0.98:
    wave = wave * (0.95 / peak)  # global gain, never dynamic processing
output = Path("mishnah_voxcpm2_mature_hebrew_test.wav")
sr = int(model.tts_model.sample_rate)
sf.write(output, wave, sr, subtype="PCM_16")
report = {"model": "openbmb/VoxCPM2", "seed": 731,
          "length_seconds": round(len(wave) / sr, 2), "sample_rate": sr,
          "raw_peak": peak, "voice_description": VOICE_DESC,
          "text": HEBREW_TEXT,
          "evaluated_by_human": False,
          "narrator_approved": False,
          "notes": "Audio created if this cell finishes; Hebrew accent, age and stability require listening."}
Path("mishnah_voxcpm2_mature_hebrew_test.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("Created", output, report["length_seconds"], "seconds")
