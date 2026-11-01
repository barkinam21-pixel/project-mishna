"""Offline PRIVATE 75s staging storyreel for Berakhot 1:1.

Storyboard typography + optional previously existing PRIVATE art only. No AI image
creation, no fal.ai traffic, no money. Does NOT pretend to contain 16 originals.
Output is a technical animatic with placeholders, intentional silence and draft
Hebrew cards, NOT a reviewed film, accepted art or published production.

Usage: python tools/private_storyreel.py PACK CAPTIONS --output-dir DIR [--reference-image EXISTING_PRIVATE_PNG] [--render]
Default is no render, only a text plan; never overwrites a previous review.
"""
from __future__ import annotations
import argparse, json, re, subprocess, shutil, hashlib
from pathlib import Path

FPS=24
EXPECTED_IDS=[f'SH{i:02d}' for i in range(1,17)]
SCENE_NAMES={
  'S01':'השאלה', 'S02':'הכהנים והתרומה',
  'S03':'שלוש דעות', 'S04':'בני רבן גמליאל', 'S05':'גבול הזמן',
}
SHOT_TITLES=[
 'ערב יורד','המנחה מציב שאלה','הכוכבים הראשונים','כהן חוזר לביתו',
 'פרט: כלי וסעודה','רבי אליעזר — דעה נפרדת','חכמים — ללא זיהוי אישים',
 'רבן גמליאל — דעה נפרדת','חזרה מן המשתה','הבנים פונים לאביהם',
 'מעבר לכתף','תגובת האב','מחווה ותגובה','חצות — המושג','עמוד השחר','סיום ופתיחת הלימוד',
]


def plan(pack:dict,captions:dict):
    if pack.get('episode_id')!='berakhot-01-01' or pack.get('status')!='dry_run_prompts_only':
        raise ValueError('Cannot build storyreel from a non-dry-run pack')
    auth=pack.get('authorization',{})
    if auth.get('paid_request_authorized') is not False or auth.get('image_generation_in_chatgpt_allowed') is not False:
        raise ValueError('Unsafe authorization state')
    shots=pack.get('shots',[])
    cues=captions.get('cues',[])
    if len(shots)!=16 or len(cues)!=16 or captions.get('captions_approved') is not False:
        raise ValueError('Expected exactly 16 unapproved caption/shot cards')
    prev=0
    for i,(s,c) in enumerate(zip(shots,cues)):
        if s.get('id')!=EXPECTED_IDS[i] or c.get('shot_id')!=EXPECTED_IDS[i]:
            raise ValueError(f'Shot and caption {i+1} mismatch')
        if s.get('start_frame')!=prev or s.get('duration_frames')!=s.get('end_frame')-prev:
            raise ValueError(f'Non-contiguous shot at {i+1}')
        if s.get('asset_status')!='not_generated':
            raise ValueError('Only placeholder storyreels are permitted')
        if not c.get('text') or not c.get('source_layer'):
            raise ValueError('Missing Hebrew caption or evidence layer')
        if len(c['text'])>75 or re.search('[\u202a-\u202e\u2066-\u2069\ufffd]',c['text']):
            raise ValueError('Invalid caption text length/encoding')
        prev=s['end_frame']
    if prev!=1800:
        raise ValueError('Must span exactly 1800 frames at 24fps')
    return {'status':'PRIVATE_PREVIS_PLAN_ONLY','fps':FPS,'frames':1800,'seconds':75,
            'shots':16,'original_ai_illustrations_generated':0,
            'illustrations_included':0,'temporary_storyboard_cards':16,
            'sound':'intentional_silence','source_approved':False,
            'external_paid_api_calls':0,'external_cost_usd':0,'workspace_usage':'unknown'}


def font_path():
    for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                 '/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf']:
        if Path(path).exists():return path
    raise RuntimeError('Missing Noto Sans Hebrew font')


def rtl(draw,xy,string,font,fill,anchor='ra'):
    draw.text(xy,string,font=font,fill=fill,direction='rtl',anchor=anchor,language='he')


def create_cards(pack,captions,dest:Path,reference:Path|None=None):
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    colors={'S01':(19,28,49),'S02':(26,31,45),'S03':(24,28,54),
            'S04':(41,31,38),'S05':(33,35,44)}
    font=font_path()
    titlef=ImageFont.truetype(font,47)
    bodyf=ImageFont.truetype(font,36)
    smallf=ImageFont.truetype(font,24)
    tinyf=ImageFont.truetype(font,19)
    ref=None
    if reference:
        if not reference.exists() or reference.suffix.lower() not in ('.png','.jpg','.jpeg'):
            raise ValueError('Private reference image missing or unsupported')
        ref=Image.open(reference).convert('RGB').resize((1280,720),Image.Resampling.LANCZOS)
    dest.mkdir(parents=True,exist_ok=True)
    files=[]
    for i,(s,c) in enumerate(zip(pack['shots'],captions['cues'])):
        sc=s['scene_id']
        img=Image.new('RGB',(1280,720),colors[sc])
        if i==0 and ref is not None:
            # Preview the already-existing user-approved style candidate for SH01 only.
            # Render it dimmed for legible typographic overlays; no new artwork created.
            img=Image.blend(img,ref,0.68)
        draw=ImageDraw.Draw(img)
        draw.rounded_rectangle((46,40,1234,680),radius=18,outline=(122,107,86),width=2)
        draw.rectangle((46,40,1234,48),fill=(181,130,78))
        rtl(draw,(1200,87),'קולנוע המשנה  |  לוח בימוי זמני',smallf,(245,223,187))
        rtl(draw,(1200,150),SCENE_NAMES[sc],titlef,(245,232,213))
        rtl(draw,(1200,205),SHOT_TITLES[i],bodyf,(234,215,188))
        rtl(draw,(1200,261),f'שוט {s["id"]}    ·    {s["duration_frames"]/24:.0f} שניות',smallf,(196,198,209))
        # Central framing schematic for missing art; not a painted illustration.
        if i!=0 or ref is None:
            left,top,right,bottom=124,300,1156,525
            draw.rounded_rectangle((left,top,right,bottom),radius=10,outline=(114,123,139),width=2)
            draw.line((left+8,top+5,right-8,bottom-5),fill=(81,91,108),width=2)
            draw.line((left+8,bottom-5,right-8,top+5),fill=(81,91,108),width=2)
            rtl(draw,(1105,425),'כאן ייכנס איור מקורי מ־fal.ai',bodyf,(174,182,193))
        draw.rounded_rectangle((84,552,1196,622),radius=10,fill=(10,12,21))
        rtl(draw,(1153,583),c['text'],bodyf,(255,244,222),anchor='ra')
        rtl(draw,(1153,656),'שכבת מקור: '+c['source_layer']+'  |  טיוטה, לא לפרסום',tinyf,(212,194,165))
        fn=dest/f'{s["id"]}.png'
        img.save(fn,optimize=True)
        files.append(fn)
    return files


def write_subtitle_files(pack,captions,dest):
    # Timing derives exactly from canonical frame integers, not rounded floats.
    def tc(fr,kind):
        ms=round(fr*1000/FPS)
        h,rest=divmod(ms,3600000);m,rest=divmod(rest,60000);s,milli=divmod(rest,1000)
        return f'{h:02d}:{m:02d}:{s:02d}{"," if kind=="srt" else "."}{milli:03d}'
    srt=[];vtt=['WEBVTT','']
    for i,(shot,cue) in enumerate(zip(pack['shots'],captions['cues']),1):
        # Don't serialize a false approved literal Mishnah quote.
        text=cue['text']
        srt.extend([str(i),f'{tc(shot["start_frame"],"srt")} --> {tc(shot["end_frame"],"srt")}',text,''])
        vtt.extend([f'{tc(shot["start_frame"],"vtt")} --> {tc(shot["end_frame"],"vtt")}',text,''])
    (dest/'private_storyreel_draft.srt').write_text('\n'.join(srt),encoding='utf-8')
    (dest/'private_storyreel_draft.vtt').write_text('\n'.join(vtt),encoding='utf-8')


def render(pack,captions,output_dir:Path,reference:Path|None):
    import json
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('ffmpeg and ffprobe required')
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError('Output directory must not contain prior output')
    output_dir.mkdir(parents=True,exist_ok=True)
    cards=create_cards(pack,captions,output_dir/'cards',reference)
    write_subtitle_files(pack,captions,output_dir)
    concat=['ffconcat version 1.0']
    for fn,shot in zip(cards,pack['shots']):
        concat.append('file '+"'"+str(fn).replace("'","'\\''")+"'")
        concat.append('duration '+str(shot['duration_frames']/FPS))
    concat.append('file '+"'"+str(cards[-1]).replace("'","'\\''")+"'")
    cfg=output_dir/'concat.ffcat'
    cfg.write_text('\n'.join(concat)+'\n',encoding='utf-8')
    output=output_dir/'Mishnah_Berakhot_1_1_PRIVATE_PREVIS_75s.mp4'
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-safe','0',
         '-f','concat','-i',str(cfg),'-vf','fps=24,format=yuv420p',
         '-frames:v','1800','-an','-c:v','libx264','-preset','fast','-crf','21',
         '-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709',
         '-colorspace','bt709','-movflags','+faststart',str(output)]
    subprocess.run(cmd,check=True,timeout=150)
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                          '-show_entries','stream=nb_frames,avg_frame_rate,width,height',
                          '-show_entries','format=duration','-of','json',str(output)],
                          check=True,capture_output=True,text=True,timeout=20)
    meta=json.loads(probe.stdout);v=meta['streams'][0]
    if int(v['nb_frames'])!=1800 or abs(float(meta['format']['duration'])-75)>0.01 or v['avg_frame_rate']!='24/1':
        raise RuntimeError('Storyboard failed CFR/frame-count verification')
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True,timeout=150)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    result={'status':'PRIVATE_TECHNICAL_STORYREEL_RENDERED','video':str(output),
            'frames':1800,'fps':24,'seconds':75,'caption_cues':len(captions['cues']),
            'originals_generated':0,'placeholders':15 if reference else 16,
            'existing_private_art_preview':1 if reference else 0,
            'audio':'intentional_silence','sha256':digest,
            'new_paid_requests':0,'external_cost_usd':0,'plan_usage':'unknown',
            'NOT_FINAL':True,'NOT_SOURCE_APPROVED':True,'NOT_VISUAL_APPROVED':True}
    (output_dir/'render-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pack',type=Path)
    p.add_argument('captions',type=Path)
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--reference-image',type=Path)
    p.add_argument('--render',action='store_true')
    a=p.parse_args()
    try:
        pack=json.loads(a.pack.read_text(encoding='utf-8'))
        caps=json.loads(a.captions.read_text(encoding='utf-8'))
        result=plan(pack,caps)
        if a.render:
            if not a.output_dir:raise ValueError('--output-dir required to render')
            result=render(pack,caps,a.output_dir,a.reference_image)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as e:
        print(json.dumps({'status':'REJECTED','error':str(e)},ensure_ascii=False))
        return 2

if __name__=='__main__':raise SystemExit(main())