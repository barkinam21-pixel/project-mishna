"""Offline FLUX.3 Image Klein layout adapter. Never generates, uploads or invokes a model.

Director layout: integer 0..1000 [top,left,bottom,right].
BFL official --boxes CLI: float 0..1 [top,left,bottom,right].
"""
import argparse
import json
from pathlib import Path
import re

MODEL = "black-forest-labs/flux-3-image-klein"
ID = re.compile(r"^[a-z][a-z0-9_]*$")


class LayoutError(ValueError):
    pass


def compile_layout(spec):
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise LayoutError("SCHEMA_VERSION_INVALID")
    if spec.get("model") != MODEL:
        raise LayoutError("MODEL_NOT_SUPPORTED")
    if spec.get("generation_authorized") is not False:
        raise LayoutError("GENERATION_AUTHORIZATION_MUST_BE_FALSE")
    if spec.get("reference_images_uploaded") is not False:
        raise LayoutError("REFERENCE_UPLOAD_NOT_PERMITTED")
    if spec.get("shot_id") != "OPN02" or spec.get("scene_id") != "INTRO-A1-S01":
        raise LayoutError("UNVERIFIED_SHOT_OR_SCENE")
    if spec.get("source_layer") != "symbolic_dramatization":
        raise LayoutError("SOURCE_LAYER_UNVERIFIED")
    if spec.get("canvas") != {"width": 1024, "height": 576}:
        raise LayoutError("CANVAS_NOT_APPROVED")
    caption = spec.get("caption")
    if not isinstance(caption, str) or len(caption.strip()) < 80 or "\n" in caption:
        raise LayoutError("CAPTION_INVALID")
    if not all(term in caption.lower() for term in ("rear", "painted", "sunset")):
        raise LayoutError("SCENE_DIRECTION_MISSING")
    rows = spec.get("boxes_1000")
    if not isinstance(rows, list) or len(rows) != 4:
        raise LayoutError("EXPECTED_FOUR_LAYOUT_ELEMENTS")
    expected = {"elder_1", "younger_1", "village_1", "landscape_1"}
    if {r.get("id") for r in rows if isinstance(r, dict)} != expected:
        raise LayoutError("MISSING_OR_DUPLICATE_LAYOUT_ID")
    boxes, coords = [], {}
    for item in rows:
        if not isinstance(item, dict) or set(item) != {"id", "bbox", "desc"}:
            raise LayoutError("UNEXPECTED_LAYOUT_FIELDS")
        identity = item["id"]
        if not ID.fullmatch(identity):
            raise LayoutError("INVALID_LAYOUT_ID")
        raw = item["bbox"]
        if not isinstance(raw, list) or len(raw) != 4 or any(
            type(n) is not int or n < 0 or n > 1000 for n in raw
        ):
            raise LayoutError("BBOX_MUST_BE_FOUR_0_TO_1000_INTEGERS")
        top, left, bottom, right = raw
        if top >= bottom or left >= right:
            raise LayoutError("BBOX_EDGES_REVERSED")
        if not isinstance(item["desc"], str) or len(item["desc"].strip()) < 15:
            raise LayoutError("ELEMENT_DESCRIPTION_TOO_SHORT")
        coords[identity] = raw
        boxes.append({"id": identity, "desc": item["desc"], "bbox": [n / 1000 for n in raw]})
    for person in ("elder_1", "younger_1"):
        top, left, bottom, right = coords[person]
        if not 250 <= bottom - top <= 350 or not 600 <= top <= 700 or bottom > 960:
            raise LayoutError("TRAVELER_SCALE_OR_DEPTH_OUTSIDE_25_35_PERCENT")
    if coords["elder_1"][3] >= coords["younger_1"][1]:
        raise LayoutError("CHARACTER_LEFT_RIGHT_ORDER_OR_OVERLAP")
    if coords["village_1"][2] - coords["village_1"][0] > 130:
        raise LayoutError("VILLAGE_NOT_DISTANT")
    if coords["landscape_1"] != [0, 0, 1000, 1000]:
        raise LayoutError("LANDSCAPE_MUST_COVER_SCENE")
    for item in boxes:
        if "<" + item["id"] + ">" not in caption:
            raise LayoutError("CAPTION_MISSING_ID:" + item["id"])
    return boxes


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline layout check; no inference or API calls")
    p.add_argument("spec", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    try:
        source = json.loads(args.spec.read_text(encoding="utf-8"))
        boxes = compile_layout(source)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error), "image_requests": 0}))
        return 2
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(boxes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "LAYOUT_VALIDATED_ONLY", "shot": "OPN02", "boxes": len(boxes),
        "official_cli_box_units": "0_to_1", "image_requests": 0, "external_usd": 0,
        "workspace_usage": "unknown", "image_generated": False,
        "production_approved": False, "output": str(args.out) if args.out else None
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
