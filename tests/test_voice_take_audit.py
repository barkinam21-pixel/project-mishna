import tempfile
from pathlib import Path
import unittest
import wave

from tools.voice_take_audit import validate


def fixture(path, duration=48000, rate=48000):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((b"\x01\x01" * duration))


class VoiceTakeTests(unittest.TestCase):
    def manifest(self):
        return {"fps": 24, "sample_rate": 48000, "release_authorized": False,
                "segments": [{"id": "N01", "speaker": "narrator", "spoken_text": "מה מחזיק עם לאורך הדורות",
                              "pronunciation_text": "מה מחזיק עם לאורך הדורות",
                              "source_status": "dramatization", "audio_path": "n01.wav",
                              "start_frame": 0, "end_frame": 96}]}

    def test_no_recording_is_not_voice_approval(self):
        with tempfile.TemporaryDirectory() as root:
            report = validate(self.manifest(), Path(root))
            self.assertEqual(report["status"], "MISSING_RECORDINGS")
            self.assertFalse(report["human_pronunciation_verified"])
            self.assertEqual(report["missing_recordings"], 1)

    def test_measured_wav_not_compliance_or_human_review(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(Path(root) / "n01.wav", duration=48000)
            report = validate(self.manifest(), Path(root))
            self.assertEqual(report["status"], "WAV_TIMING_MEASURED_NOT_VOICE_APPROVED")
            self.assertEqual(report["rows"][0]["remaining_slot_seconds"], 3)
            self.assertFalse(report["expressive_performance_verified"])

    def test_overlong_audio_is_error(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(Path(root) / "n01.wav", duration=240000)
            report = validate(self.manifest(), Path(root))
            self.assertEqual(report["status"], "INVALID")
            self.assertTrue(any("exceeds" in x for x in report["errors"]))

    def test_bad_rate_and_overlap(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(Path(root) / "n01.wav", rate=44100)
            report = validate(self.manifest(), Path(root))
            self.assertEqual(report["status"], "INVALID")
            self.assertTrue(any("48kHz" in x for x in report["errors"]))
        manifest = self.manifest()
        manifest["segments"].append(dict(manifest["segments"][0], id="N02", start_frame=48, end_frame=140))
        report = validate(manifest, Path("."))
        self.assertEqual(report["status"], "INVALID")

    def test_path_traversal_rejected(self):
        manifest = self.manifest()
        manifest["segments"][0]["audio_path"] = "../x.wav"
        self.assertEqual(validate(manifest, Path("."))["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
