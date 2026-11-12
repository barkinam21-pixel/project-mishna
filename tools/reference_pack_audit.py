"""Offline full/subset/corrected Mishnah reference pack consistency and format audit.

The first two ZIPs intentionally embed a *27-record* master inventory even though
only eight source images are in the subset. The corrected ZIP contains exactly
those eight and corrects six misleading .png extensions on JPEG bytes.
No files are extracted or changed; no approvals, uploads, or network calls.
"""
import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from PIL import Image

ROLES = {"00_PRIMARY_REFERENCE":2,"01_ACTIVE_GUIDES":6,
         "02_CONTEXT_ONLY":14,"03_HOLD_NOT_FOR_MODEL":5}
ACTIVE = {"00_PRIMARY_REFERENCE","01_ACTIVE_GUIDES"}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def open_checked(path):
    path=Path(path)
    if path.stat().st_size>40_000_000:
        raise ValueError("Reference archive exceeds safety cap")
    raw=path.read_bytes()
    z=ZipFile(io.BytesIO(raw))
    names=z.namelist()
    if len(names)!=len(set(names)) or len(names)>100 or sum(i.file_size for i in z.infolist())>50_000_000:
        z.close()
        raise ValueError("Unsafe reference ZIP contents")
    if z.testzip() is not None:
        z.close()
        raise ValueError("Reference ZIP CRC error")
    return z,digest(raw)


def inspect_image(data):
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ('PNG','JPEG') or im.width<64 or im.height<64 or im.width*im.height>30_000_000:
            raise ValueError("Unsupported reference image")
        kind=im.format
        im.verify()
    return kind


def audit(full_path,subset_path,corrected_path):
    full,hs=open_checked(full_path)
    subset,ss=open_checked(subset_path)
    corrected,cs=open_checked(corrected_path)
    try:
        old_master=full.read('manifest.json')
        if old_master!=subset.read('manifest.json'):
            raise ValueError("Historic subset must retain matching master inventory")
        source=json.loads(old_master)
        records=source.get('records',[])
        roles=dict(Counter(r.get('category') for r in records))
        if roles!=ROLES or len(records)!=27:
            raise ValueError("Unexpected master inventory")
        latest=json.loads(corrected.read('manifest.json'))
        revised=latest.get('records',[])
        if len(revised)!=8 or latest.get('status')!='PRIVATE_REFERENCE_ONLY_NOT_APPROVED_FOR_PROVIDER_UPLOAD':
            raise ValueError("Corrected subset is not an eight-image private reference pack")
        if latest.get('source_full_archive_sha256')!=hs or latest.get('source_curated_archive_sha256')!=ss:
            raise ValueError("Corrected pack source lineage mismatch")
        revised_by_source={r['source_archive_path']:r for r in revised}
        if len(revised_by_source)!=8:
            raise ValueError("Duplicate corrected source references")
        from_full=set()
        from_old_subset=set()
        from_corrected=set()
        mislabeled=0
        corrected_extensions=0
        for r in records:
            p=r.get('archive_path')
            category=r.get('category')
            if category not in ROLES or not isinstance(p,str) or not p.startswith(category+'/'):
                raise ValueError("Invalid reference role or path")
            if p in from_full or p not in full.namelist():
                raise ValueError("Missing/duplicate image in master archive")
            from_full.add(p)
            blob=full.read(p)
            if digest(blob)!=r.get('sha256'):
                raise ValueError("Source record hash mismatch")
            fmt=inspect_image(blob)
            wrong_ext=not p.lower().endswith('.jpg' if fmt=='JPEG' else '.png')
            mislabeled+=int(wrong_ext)
            if r.get('provider_upload_allowed') is not False or r.get('release_approved') is not False:
                raise ValueError("Original reference permissions unexpectedly open")
            if category in ACTIVE:
                if p not in subset.namelist() or subset.read(p)!=blob:
                    raise ValueError("Old subset lost or changed active reference")
                from_old_subset.add(p)
                r2=revised_by_source.get(p)
                if not isinstance(r2,dict):
                    raise ValueError("Active reference omitted from corrected manifest")
                q=r2.get('archive_path')
                if not isinstance(q,str) or q in from_corrected or q not in corrected.namelist():
                    raise ValueError("Missing/duplicate corrected image")
                from_corrected.add(q)
                if not q.endswith('.jpg' if fmt=='JPEG' else '.png') or corrected.read(q)!=blob:
                    raise ValueError("Corrected extension or original bytes do not match")
                if r2.get('sha256')!=digest(blob) or r2.get('provider_upload_allowed') is not False or r2.get('release_approved') is not False:
                    raise ValueError("Corrected hash/rights gate mismatch")
                corrected_extensions+=int(p!=q)
            elif p in subset.namelist() or p in revised_by_source:
                raise ValueError("Context/hold reference erroneously active")
        if {n for n in full.namelist() if n.endswith(('.png','.jpg')) and n.startswith(tuple(ROLES))}!=from_full:
            raise ValueError("Unexpected master image")
        if {n for n in subset.namelist() if n.startswith(tuple(ROLES))}!=from_old_subset:
            raise ValueError("Unexpected historic subset image")
        if {n for n in corrected.namelist() if n.startswith(tuple(ROLES))}!=from_corrected:
            raise ValueError("Unexpected corrected subset image")
        if mislabeled!=25 or corrected_extensions!=6:
            raise ValueError("Unexpected format correction count")
        return {"status":"VERIFIED_PRIVATE_FORMAT_CORRECTION", "source_full_sha256":hs,
                "source_curated_sha256":ss, "corrected_sha256":cs,
                "full_reference_count":len(from_full),"curated_reference_count":len(from_corrected),
                "retained_context_and_hold":len(from_full)-len(from_corrected),
                "original_extension_mismatches":mislabeled,
                "corrected_file_extensions":corrected_extensions,
                "images_reencoded":0, "provider_calls":0,
                "rights_or_publication_approved":False,
                "workspace_usage":"unknown"}
    finally:
        full.close();subset.close();corrected.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full',required=True)
    p.add_argument('--curated',required=True)
    p.add_argument('--corrected',required=True)
    p.add_argument('--out')
    x=p.parse_args()
    result=audit(x.full,x.curated,x.corrected)
    if x.out:
        dest=Path(x.out)
        if dest.suffix!='.json':raise ValueError('Report must be JSON')
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()