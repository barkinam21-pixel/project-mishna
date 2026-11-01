"""Short, synthetic-only FFmpeg integration check. This is NOT a Mishnah film.

Uses two artificial colored 2x2 PNGs, one generated electronic beep and one
technical Hebrew test caption for 48 frames. Nothing is archived or uploaded.
Its ONLY purpose is to catch FFmpeg filter/stream/codec mistakes before real
illustrations and spoken recordings exist.
"""
from array import array
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
import zlib

from tools import hebrew_captions
from tools import private_proof_assembler as proof


def png_chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def test_only_png(path, rgb):
    pixels = b"".join(b"\x00" + bytes(rgb) * 2 for _ in range(2))
    image = (b"\x89PNG\r\n\x1a\n"
             + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
             + png_chunk(b"IDAT", zlib.compress(pixels))
             + png_chunk(b"IEND", b""))
    path.write_bytes(image)


class FFmpegFilterSmoke(unittest.TestCase):
    def test_two_shot_synthetic_not_a_film(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg unavailable: filter smoke not run")
        with tempfile.TemporaryDirectory(prefix="mishna-TEST-ONLY-") as directory:
            root = Path(directory)
            (root / "media").mkdir()
            test_only_png(root / "media/one.png", (12, 55, 65))
            test_only_png(root / "media/two.png", (55, 22, 12))
            wav_path = root / "media/TEST_ONLY_TONE.wav"
            samples = array("h", (int(2500 * math.sin(2 * math.pi * 440 * i / 48000))
                                  for i in range(48000)))
            with wave.open(str(wav_path), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(48000)
                f.writeframes(samples.tobytes())
            (root / "private-captions.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nבדיקה טכנית בלבד\n\n",
                encoding="utf-8")
            (root / "private-captions.ass").write_text(
                hebrew_captions.ASS_HEADER +
                "Dialogue: 0,0:00:00.00,0:00:02.00,Hebrew,,0,0,0,,בדיקה טכנית בלבד\n",
                encoding="utf-8")
            blueprint = {
                "target_duration_frames": 48,
                "shots": [
                    {"id": "T01", "duration_frames": 24},
                    {"id": "T02", "duration_frames": 24},
                ],
            }
            cfg = {"images": [
                {"shot_id": "T01", "path": "media/one.png"},
                {"shot_id": "T02", "path": "media/two.png"},
            ], "voice_takes": [
                {"start_frame": 0, "path": "media/TEST_ONLY_TONE.wav"}
            ]}
            command = proof.ffmpeg_args(cfg, blueprint, root, root)
            self.assertIn("48", command)
            subprocess.run(command, cwd=root, check=True,
                           capture_output=True, text=True, timeout=100)
            result = root / "private-review.mp4"
            self.assertTrue(result.exists())
            self.assertTrue(proof.verify_video(result, total_frames=48))
            # TemporaryDirectory deletes everything; never publish test tones.
            self.assertLess(result.stat().st_size, 5000000)


if __name__ == "__main__":
    unittest.main()
