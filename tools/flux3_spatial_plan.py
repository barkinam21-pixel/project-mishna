"""Fail-closed offline layout export for BFL's FLUX 3 Image Klein CLI.

This module NEVER imports an inference backend, opens URLs, or loads private media.
Vendor CLI boxes use normalized [y_min, x_min, y_max, x_max] coordinates.
"""
import argparse
import json
import math
import os
from pathlib import Path
import tempfile

MODEL = 'black-forest-labs/flux-3-image-klein'
IDS = ('older_traveler', 'younger_traveler', 'distant_village')


def validate(spec):
    if not isinstance(spec, dict) or spec.get('schema_version') != 1:
        raise ValueError('INVALID_LAYOUT_SCHEMA')
    if spec.get('model') != MODEL or spec.get('shot_id') != 'OPN02':
        raise ValueError('WRONG_MODEL_OR_SHOT')
    if spec.get('source_layer') != 'symbolic_dramatization_not_documented_event':
        raise ValueError('SOURCE_LAYER_MUST_BE_EXPLICIT')
    if spec.get('width') != 1024 or spec.get('height') != 576:
        raise ValueError('UNEXPECTED_CANVAS')
    if not isinstance(spec.get('prompt'), str) or len(spec['prompt'].strip()) < 40:
        raise ValueError('SHOT_PROMPT_REQUIRED')
    if spec.get('generation_authorized') is not False or spec.get('release_authorized') is not False:
        raise ValueError('NO_GENERATION_OR_RELEASE_AUTHORIZATION')
    if spec.get('api_mode') != 'self_hosted_only' or spec.get('external_spend_limit_usd') != 0:
        raise ValueError('NO_PAID_API_OR_SPEND_ALLOWED')
    boxes = spec.get('boxes')
    if not isinstance(boxes, list) or len(boxes) != len(IDS):
        raise ValueError('EXPECTED_THREE_LAYOUT_BOXES')
    by_id = {}
    for box in boxes:
        if not isinstance(box, dict) or set(box) != {'id', 'desc', 'bbox'}:
            raise ValueError('BAD_VENDOR_BOX_SHAPE')
        ident, desc, bbox = box['id'], box['desc'], box['bbox']
        if ident in by_id or ident not in IDS:
            raise ValueError('DUPLICATE_OR_UNKNOWN_ID')
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError('DESCRIPTION_REQUIRED')
        if not isinstance(bbox, list) or len(bbox) != 4 or any(
            type(n) not in (int, float) or not math.isfinite(n) or n < 0 or n > 1 for n in bbox
        ):
            raise ValueError('INVALID_NORMALIZED_BOX')
        y0, x0, y1, x1 = bbox
        if y0 >= y1 or x0 >= x1:
            raise ValueError('INVERTED_OR_EMPTY_BOX')
        by_id[ident] = box
    if set(by_id) != set(IDS):
        raise ValueError('REQUIRED_OBJECT_MISSING')
    older = by_id['older_traveler']['bbox']
    younger = by_id['younger_traveler']['bbox']
    village = by_id['distant_village']['bbox']
    for b in (older, younger):
        if not .25 <= b[2] - b[0] <= .35:
            raise ValueError('TRAVELER_HEIGHT_MUST_BE_25_TO_35_PERCENT')
        if b[2] < .75:
            raise ValueError('TRAVELERS_SHOULD_BE_NEAR_LOWER_FRAME')
    if (older[1] + older[3]) / 2 >= (younger[1] + younger[3]) / 2:
        raise ValueError('TRAVELER_LEFT_RIGHT_ORDER')
    if village[2] - village[0] >= .15:
        raise ValueError('VILLAGE_NOT_DISTANT_ENOUGH')
    if 'private_reference' in spec or 'image_data' in spec or 'credentials' in spec:
        raise ValueError('PRIVATE_ASSET_METADATA_FORBIDDEN')
    return boxes


def export_plan(spec):
    boxes = validate(spec)
    return {
        'status': 'LAYOUT_VALIDATED_OFFLINE_ONLY',
        'shot_id': spec['shot_id'],
        'model': MODEL,
        'vendor_cli_boxes': boxes,
        'prompt': spec['prompt'],
        'target_traveler_height_percent': [25, 35],
        'layout_accuracy': 'MODEL_GUIDANCE_NOT_HARD_MASK_NOT_GENERATION_PROOF',
        'blocked': [
            'PRIVATE_ZERO_COST_GPU_NOT_VERIFIED',
            'PRIVATE_REFERENCE_AVAILABILITY_AND_RIGHTS_UNVERIFIED',
            'MODEL_WEIGHTS_AND_PROMPT_UPSAMPLER_NOT_PROVISIONED',
            'NEW_IMAGE_GENERATION_NOT_AUTHORIZED',
            'HUMAN_IMAGE_AND_SOURCE_REVIEW_REQUIRED',
        ],
        'provider_requests': 0,
        'external_spend_initiated_usd': 0,
        'workspace_usage': 'unknown',
        'generated_image': None,
        'accepted': False,
    }


def write_private_boxes(root, output, boxes):
    root = Path(root).resolve()
    dest = Path(output)
    dest = (root / dest).resolve() if not dest.is_absolute() else dest.resolve()
    private = (root / 'private-media').resolve()
    if private not in dest.parents:
        raise ValueError('OUTPUT_MUST_BE_INSIDE_PRIVATE_MEDIA')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.flux3-', suffix='.json', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(boxes, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return str(dest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout')
    parser.add_argument('--root', default='.')
    parser.add_argument('--boxes-out', help='Export only BFL boxes JSON inside private-media')
    args = parser.parse_args(argv)
    layout_path = Path(args.root).resolve() / args.layout
    spec = json.loads(layout_path.read_text(encoding='utf-8'))
    result = export_plan(spec)
    if args.boxes_out:
        result['private_boxes_path'] = write_private_boxes(args.root, args.boxes_out, result['vendor_cli_boxes'])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
