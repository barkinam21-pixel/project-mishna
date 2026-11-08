"""Private one-board review for a whole scene; no provider calls, no approvals.

Only locally hash-verified images may appear. A remote candidate whose bytes are
unavailable is represented by a placeholder, not an invented or public asset.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from tools.comfy_scene_images import under
from tools.scene_pack_preflight import EXPECTED_IDS, verified_entry

CELL_W, CELL_H = 480, 315
IMAGE_W, IMAGE_H = 456, 256
MARGIN, HEADER = 12, 54


def render_board(report, state, root, output):
    if [s.get("shot_id") for s in report.get("shots", [])] != EXPECTED_IDS:
        raise ValueError("Unexpected scene shot list")
    root = Path(root).resolve()
    output = under(root, str(output))
    if "private-media" not in output.relative_to(root).parts:
        raise ValueError("Review boards with possible private images must stay under private-media")
    entries = state.get("entries", {}) if isinstance(state, dict) else {}
    board = Image.new("RGB", (CELL_W * 2, HEADER + CELL_H * 4), (19, 23, 28))
    draw = ImageDraw.Draw(board)
    font = ImageFont.load_default()
    draw.text((MARGIN, 12), "MISHNAH - PRIVATE SCENE REVIEW / DRAFT ONLY", fill=(237, 224, 196), font=font)
    draw.text((MARGIN, 31), "Seven distinct original images required. Nothing is auto-approved.", fill=(185, 190, 194), font=font)
    shown = []
    for i, shot in enumerate(report["shots"]):
        x, y = (i % 2) * CELL_W, HEADER + (i // 2) * CELL_H
        image_box = (x + MARGIN, y + 32, x + MARGIN + IMAGE_W, y + 32 + IMAGE_H)
        entry = entries.get(shot.get("key"))
        status, _ = verified_entry(entry, root)
        src = None
        if status in ("VERIFIED_LOCAL_ACCEPTED", "CANDIDATE_NEEDS_HUMAN_REVIEW"):
            src = under(root, entry["path"])
        if src:
            with Image.open(src) as im:
                im.load()
                if im.width < 64 or im.height < 64 or im.width * im.height > 30_000_000:
                    raise ValueError("Invalid private image size")
                preview = ImageOps.contain(im.convert("RGB"), (IMAGE_W, IMAGE_H))
            px = image_box[0] + (IMAGE_W - preview.width) // 2
            py = image_box[1] + (IMAGE_H - preview.height) // 2
            board.paste(preview, (px, py))
            label = "LOCAL / " + ("ACCEPTED" if status == "VERIFIED_LOCAL_ACCEPTED" else "CANDIDATE")
            shown.append(shot["shot_id"])
        else:
            draw.rectangle(image_box, fill=(46, 49, 54))
            draw.text((x + 96, y + 154), "PRIVATE IMAGE NOT MOUNTED", fill=(227, 188, 130), font=font)
            label = "PLACEHOLDER - " + shot.get("status", "MISSING")
        draw.rectangle((x + 4, y + 3, x + CELL_W - 4, y + CELL_H - 4),
                       outline=(90, 82, 71), width=2)
        draw.text((x + MARGIN, y + 13), shot["shot_id"] + " | " + label[:58],
                  fill=(236, 224, 201), font=font)
        draw.text((x + MARGIN, y + 296), "No auto-approval / rights and continuity review required",
                  fill=(191, 191, 190), font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    board.save(temp, format="PNG")
    temp.replace(output)
    output.chmod(0o600)
    return {"output": str(output.relative_to(root)), "images_shown": shown,
            "placeholders": len(EXPECTED_IDS) - len(shown),
            "approval_granted": False, "provider_calls": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--report", default="build/scene-pack-preflight.json")
    p.add_argument("--state", default="private-media/director-images/state.json")
    p.add_argument("--out", default="private-media/scene-review/scene-contact-sheet.png")
    args = p.parse_args()
    root = Path(args.root).resolve()
    report = json.loads(under(root, args.report).read_text(encoding="utf-8"))
    state_path = under(root, args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    result = render_board(report, state, root, args.out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
