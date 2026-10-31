import tempfile
import unittest
from pathlib import Path
import wave

from tools.sync_probe import (
    DURATION_FRAMES, RATE, SAMPLES_PER_FRAME,
    START_FRAMES, make_srt, time_srt, write_audio,
)


class AudioVideoSyncProbeTests(unittest.TestCase):
    def test_srt_times_from_absolute_frames(self):
        cues = make_srt()
        self.assertIn("00:00:04,000", cues)
        self.assertIn("00:00:08,000", cues)
        self.assertIn("00:00:11,000", cues)
        self.assertIn("ללא קריינות", cues)
        self.assertEqual(time_srt(DURATION_FRAMES), "00:00:12,000")

    def test_exact_wave_samples(self):
        with tempfile.TemporaryDirectory() as path:
            audio = Path(path) / "clip.wav"
            meta = write_audio(audio)
            with wave.open(str(audio), "rb") as reader:
                self.assertEqual(reader.getnframes(), DURATION_FRAMES * SAMPLES_PER_FRAME)
                self.assertEqual(reader.getframerate(), RATE)
                self.assertEqual(reader.getnchannels(), 1)
            self.assertEqual(meta["pulse_start_samples"], [x * 2000 for x in START_FRAMES])

    def test_no_final_voice_claim(self):
        self.assertEqual(SAMPLES_PER_FRAME, 2000)
        self.assertEqual(DURATION_FRAMES, 288)


if __name__ == "__main__":
    unittest.main()
