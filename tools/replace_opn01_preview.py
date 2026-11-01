#!/usr/bin/env python3
"""Insert ONLY the first private cinematic OPN01 frame into the chronological 45s proof.

Offline ffmpeg assembly; default dry-run. Private PNG must be on the SAME
machine as the renderer and its SHA-256 verified. No image API or credits.
This produces a DRAFT with an unapproved first image, NOT a finished film.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from tools import visual_gate_opn01

FPS = 24
TOTAL = 1080
FIRST = 96
WIDTH, HEIGHT = 960, 540
HEBREW = 'heb'

class UnsafeMedia(ValueError):
    pass


def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        while True:
            b=f.read(1024*1024)
            if not b:break
            digest.update(b)
    return digest.hexdigest()


def json_probe(path, ffprobe='ffprobe'):
    cmd=[ffprobe,'-v','error','-show_entries',
         'format=duration:stream=index,codec_name,codec_type,width,height,nb_frames,r_frame_rate,avg_frame_rate,duration,sample_rate,channels,color_primaries,color_transfer,color_space',
         '-of','json',str(path)]
    result=subprocess.run(cmd,check=True,capture_output=True,text=True)
    return json.loads(result.stdout)


def preflight(manifest, image_path, expected_sha, source_path, *, ffprobe='ffprobe'):
    if not image_path.is_file() or not source_path.is_file():
        raise UnsafeMedia('Missing local private frame or source video')
    if not re.fullmatch('[0-9a-f]{64}',expected_sha):
        raise UnsafeMedia('Expected image SHA256 is missing or malformed')
    if sha256_file(image_path)!=expected_sha:
        raise UnsafeMedia('Private first image hash mismatch')
    if image_path.suffix.lower()!='.png' or image_path.read_bytes()[:8]!=bytes.fromhex('89504e470d0a1a0a'):
        raise UnsafeMedia('Expected original private PNG')
    shots=manifest.get('shots',[])
    if [s.get('id') for s in shots]!=[f'OPN{i:02d}' for i in range(1,8)]:
        raise UnsafeMedia('Not the original opening sequence')
    if shots[0].get('start_frame')!=0 or shots[0].get('frames')!=FIRST:
        raise UnsafeMedia('First cinematic shot timing changed')
    if shots[-1].get('end_frame')!=TOTAL:
        raise UnsafeMedia('45-second film timing changed')
    if manifest.get('next_paid_shot_candidate')!='OPN01' or not manifest.get('sons_return_scene_is_later'):
        raise UnsafeMedia('Wrong editorial shot')
    if manifest['source_contract']['source_layer']!='dramatization_only_until_next_sequence':
        raise UnsafeMedia('Source status mismatch')
    ip=json_probe(image_path,ffprobe=ffprobe)
    iv=next((s for s in ip.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not iv or iv.get('codec_name')!='png' or min(int(iv.get('width',0)),int(iv.get('height',0)))<450:
        raise UnsafeMedia('Image too small or not PNG')
    vp=json_probe(source_path,ffprobe=ffprobe)
    vs=next((s for s in vp.get('streams',[]) if s.get('codec_type')=='video'),None)
    audio=next((s for s in vp.get('streams',[]) if s.get('codec_type')=='audio'),None)
    if not vs or vs.get('codec_name')!='h264' or (vs.get('width'),vs.get('height'))!=(WIDTH,HEIGHT):
        raise UnsafeMedia('Expected verified 960x540 H.264 master blockout')
    if vs.get('r_frame_rate')!='24/1' or int(vs.get('nb_frames',0))!=TOTAL:
        raise UnsafeMedia('Source is not the 1080-frame first opening')
    if any(vs.get(k)!='bt709' for k in ('color_primaries','color_transfer','color_space')):
        raise UnsafeMedia('Source video has incorrect color metadata')
    if not audio or audio.get('sample_rate')!='48000' or audio.get('channels')!=2:
        raise UnsafeMedia('Missing original 48kHz stereo scratch audio')
    if abs(float(vp.get('format',{}).get('duration','0'))-45.0)>.025:
        raise UnsafeMedia('Source duration is not 45s')
    return {'status':'OFFLINE_EDITORIAL_PLAN_READY','first_shot':'OPN01',
            'first_frame_count':FIRST,'total_frames':TOTAL,'image_sha256':expected_sha,
            'private_media':True,'public_release_allowed':False,
            'new_paid_requests':0,'new_ai_image_generation':0}


def ass_stamp(path):
    header='''[Script Info]\nScriptType: v4.00+\nPlayResX: 960\nPlayResY: 540\nWrapStyle: 0\nScaledBorderAndShadow: yes\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Note,Noto Sans Hebrew,18,&H00E7DDD4,&H00FFFFFF,&H80101619,&H790B1016,0,0,0,0,100,100,0,0,1,1,0,9,35,30,37,1\nStyle: Main,Noto Sans Hebrew,27,&H00F6F3E9,&H00FFFFFF,&H8A101719,&H930B1015,0,0,0,0,100,100,0,0,1,2,0,2,65,65,53,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    lines=[header,
        'Dialogue: 0,0:00:00.05,0:00:03.95,Note,,0,0,0,,מועמד איור OPN01 — טרם אושר לסרט\n',
        'Dialogue: 1,0:00:00.50,0:00:03.25,Main,,0,0,0,,המחזה סמלית — לא אירוע היסטורי מתועד\n']
    path.write_text(''.join(lines),encoding='utf-8')


def render(image_path,expected_sha,source_path,manifest_path,output_path,*,dry_run=True,ffmpeg='ffmpeg',visual_review=None):
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    plan=preflight(manifest,image_path,expected_sha,source_path)
    if dry_run:
        return plan
    # The lower-level renderer was callable directly with --render, bypassing
    # finish_opn01_private's human review gate. Enforce image-specific approval
    # in BOTH entrypoints; test images cannot silently become public previews.
    visual_gate_opn01.verify_visual_gate(visual_review, expected_sha)
    if output_path.exists():
        raise UnsafeMedia('Never overwrite an existing private review render')
    output_path.parent.mkdir(parents=True,exist_ok=True)
    stamp=output_path.with_suffix('.firstshot.ass')
    ass_stamp(stamp)
    # One H.264 encode plus lossless MP4 remux; 96 frames of original private
    # illustration + 984 original blockout frames, same original scratch audio.
    subtitle=str(stamp.resolve()).replace(':','\\:').replace("'",r"\'")
    filt=(f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={WIDTH}:{HEIGHT},fps={FPS},trim=end_frame={FIRST},"
          f"setpts=PTS-STARTPTS,format=yuv420p,"
          f"fade=t=in:st=0:d=0.35,ass='{subtitle}'[hero];"
          f"[1:v]trim=start_frame={FIRST}:end_frame={TOTAL},setpts=PTS-STARTPTS[tail];"
          f"[hero][tail]concat=n=2:v=1:a=0[v]")
    with tempfile.TemporaryDirectory(prefix='opn01_private_timing_',dir=output_path.parent) as td:
        stage=Path(td)
        encoded=stage/'encoded.mp4'
        retimed=stage/'retimed.mp4'
        cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y',
             '-loop','1','-framerate',str(FPS),'-i',str(image_path),
             '-i',str(source_path),'-filter_complex',filt,
             '-map','[v]','-map','1:a:0',
             '-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p',
             '-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709',
             '-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
             '-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
             '-metadata:s:a:0','language=heb','-t','45',str(encoded)]
        subprocess.run(cmd,check=True,timeout=180)
        # concat may omit the last packet's duration in a 1MHz timebase.
        # A packet-copy remux fixes the final 1/24s and MP4 sample durations
        # without a second lossy encode or changing the soundtrack.
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y',
                        '-i',str(encoded),'-map','0:v:0','-map','0:a:0',
                        '-c','copy','-video_track_timescale','12288',
                        '-movflags','+faststart',str(retimed)],check=True,timeout=90)
        vp=json_probe(retimed)
        v=next(s for s in vp['streams'] if s['codec_type']=='video')
        if (int(v.get('nb_frames',0))!=TOTAL or v.get('r_frame_rate')!='24/1'
                or v.get('avg_frame_rate')!='24/1'
                or abs(float(v.get('duration','0'))-45.0)>.001
                or abs(float(vp['format']['duration'])-45.0)>.03):
            raise UnsafeMedia('Rendered film fails exact 24fps/45s stream-and-container timing')
        if any(v.get(k)!='bt709' for k in ('color_primaries','color_transfer','color_space')):
            raise UnsafeMedia('Color tagging failed on delivery video')
        # Decode full video and audio before exposing any final output path.
        subprocess.run([ffmpeg,'-hide_banner','-v','error','-i',str(retimed),'-f','null','-'],
                       check=True,capture_output=True,timeout=180)
        retimed.replace(output_path)
    completed={**plan,'status':'PRIVATE_DRAFT_1_OF_7_ILLUSTRATIONS_ATTACHED',
               'output_sha256':sha256_file(output_path),'actual_output':str(output_path)}
    output_path.with_suffix('.qa.json').write_text(json.dumps(completed,indent=2)+'\n')
    return completed


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=Path('episodes/berakhot-01-01/opening-45s-director-pack-v1.json'))
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--image-sha256',required=True)
    p.add_argument('--blockout',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--render',action='store_true')
    p.add_argument('--visual-review-json',type=Path,default=None,help='Private accepted image-specific human visual review required for render')
    a=p.parse_args(argv)
    try:
        result=render(a.image,a.image_sha256,a.blockout,a.manifest,a.output,dry_run=not a.render,visual_review=a.visual_review_json)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,FileNotFoundError,subprocess.SubprocessError,json.JSONDecodeError) as e:
        print('BLOCKED: '+type(e).__name__,file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())