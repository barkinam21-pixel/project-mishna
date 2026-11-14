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

def assemble_technical_fixture(root, out, caption='בדיקת מערכת — ללא קריינות'):
    """M2:15 compressed1s slots, synthetic images/sound only, NOT91s artwork.

    Extends this existing FFmpeg storyreel module. No private inputs are accepted.
    """
    import io,math,random,struct,wave
    from tools.scene_factory import within,writer_lock,digest,file_sha,SceneBlocked
    from PIL import Image,ImageDraw,ImageFont
    import unicodedata
    root=Path(root).resolve();out=within(root,str(out))
    if 'private-media' not in out.relative_to(root).parts:raise ValueError('TECHNICAL_OUTPUT_MUST_BE_PRIVATE')
    if not caption or len(caption)>42 or unicodedata.normalize('NFC',caption)!=caption or re.search('[\u202a-\u202e\u2066-\u2069\ufffd\n]',caption):raise ValueError('UNSAFE_TECHNICAL_CAPTION')
    for binary in ('ffmpeg','ffprobe','fc-match'):
        if not shutil.which(binary):raise RuntimeError('Required local tool missing: '+binary)
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    with writer_lock(out/'assembly.lock'):
        version=subprocess.check_output(['ffmpeg','-version']).decode().splitlines()[0]
        font=font_path();frames=360;width,height=960,540;sample_count=frames*2000
        config={'fixture':True,'shots':15,'frames_per_shot':24,'fps':24,'samples_per_frame':2000,'size':[width,height],'caption':caption,'pipeline_sha256':file_sha(Path(__file__)),'ffmpeg':version,'font_sha256':file_sha(Path(font))}
        key=digest(config);dest=out/key;receipt=dest/'receipt.json'
        if receipt.exists():
            r=json.loads(receipt.read_text())
            for name,h in r['outputs'].items():
                p=dest/name
                if not p.is_file() or file_sha(p)!=h:raise ValueError('TECHNICAL_CACHE_OUTPUT_CHANGED')
            return dict(r,cache_hit=True,receipt=str(receipt.relative_to(root)))
        dest.mkdir(parents=True,exist_ok=True,mode=0o700)
        pack={'shots':[{'id':f'FIX-{i+1:02d}','start_frame':i*24,'end_frame':(i+1)*24} for i in range(15)]}
        caps={'cues':[{'text':caption} for _ in pack['shots']]}
        write_subtitle_files(pack,caps,dest)
        rng=random.Random(771);pcm=bytearray();peak=0;energy=0
        # Wind and brief footstep-like test pulses: authored synthesis, not speech.
        for i in range(sample_count):
            t=i/48000;wind=.015*rng.uniform(-1,1);phase=t%1
            step=.12*math.sin(2*math.pi*90*t)*max(0,1-phase/.07) if phase<.07 else 0
            value=wind+step;peak=max(peak,abs(value));energy+=value*value
            left=int(value*30000);right=int((wind+step*.75)*30000);pcm.extend(struct.pack('<hh',left,right))
        audio=dest/'SYNTHETIC_TEST_ONLY.wav'
        with wave.open(str(audio),'wb') as w:w.setparams((2,2,48000,0,'NONE','not compressed'));w.writeframes(pcm)
        video=dest/'fixture-picture.partial.mp4';final=dest/'TECHNICAL_FIXTURE_NOT_FILM.mp4';partial=dest/'assembled.partial.mp4'
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{width}x{height}','-r','24','-i','pipe:0','-an','-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(video)]
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        contact=Image.new('RGB',(width//3*3,height//3*5))
        try:
            fnt=ImageFont.truetype(str(font),24)
            for frame in range(frames):
                shot=frame//24;local=frame%24;im=Image.new('RGB',(width,height),(35+shot*8,55+shot*4,85+shot*4));d=ImageDraw.Draw(im)
                d.text((30,25),'TECHNICAL FIXTURE / NO NARRATION / NOT A FILM',font=fnt,fill='white')
                d.text((30,65),f'FIX-{shot+1:02d} | frame {frame:03d} / 359',font=fnt,fill='white')
                x=100+local*18;d.rectangle((x,180,x+100,280),fill=(210,170,100))
                # Deliberate observable test motion, not reused production art.
                d.line((0,420,width,420),fill='white',width=3)
                if local==12:
                    preview=im.resize((width//3,height//3));contact.paste(preview,((shot%3)*(width//3),(shot//3)*(height//3)))
                proc.stdin.write(im.tobytes())
            proc.stdin.close()
            err=proc.stderr.read();rc=proc.wait(timeout=90)
            if rc:raise RuntimeError('FFmpeg fixture picture encoding failed')
        except Exception:
            proc.kill();proc.wait();raise
        contact.save(dest/'technical-contact-sheet.png')
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),'-i',str(audio),'-i','private_storyreel_draft.srt','-vf',"subtitles=private_storyreel_draft.srt:force_style='FontName=Noto Sans Hebrew,FontSize=22,MarginV=32',setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709",'-map','0:v:0','-map','1:a:0','-map','2:s:0','-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','aac','-ar','48000','-ac','2','-c:s','mov_text','-metadata:s:a:0','language=heb','-metadata:s:s:0','language=heb','-movflags','+faststart',str(partial)]
        subprocess.run(cmd,cwd=dest,check=True,capture_output=True,timeout=90)
        meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(partial)]))
        v=next(s for s in meta['streams'] if s['codec_type']=='video');a=next(s for s in meta['streams'] if s['codec_type']=='audio');sub=next(s for s in meta['streams'] if s['codec_type']=='subtitle')
        if (v['codec_name']!='h264' or v['pix_fmt']!='yuv420p' or v['avg_frame_rate']!='24/1' or int(v['nb_read_frames'])!=frames or [v['width'],v['height']]!=[width,height] or any(v.get(k)!='bt709' for k in ('color_space','color_transfer','color_primaries')) or a['codec_name']!='aac' or a['sample_rate']!='48000' or a['channels']!=2 or sub.get('tags',{}).get('language')!='heb' or abs(float(meta['format']['duration'])-frames/24)>.042):raise ValueError('TECHNICAL_PROBE_FAILED')
        decoded=subprocess.run(['ffmpeg','-hide_banner','-i',str(partial),'-vf','blackdetect=d=0.1:pix_th=0.05,freezedetect=n=-60dB:d=0.5','-f','null','-'],capture_output=True,text=True,timeout=90)
        if decoded.returncode or 'black_start:' in decoded.stderr or 'freeze_start:' in decoded.stderr:raise ValueError('TECHNICAL_DECODE_BLACK_OR_FREEZE_FAILED')
        if not .001<math.sqrt(energy/sample_count)<.2 or peak>.8:raise ValueError('SYNTHETIC_SOUND_INVALID')
        partial.replace(final);video.unlink(missing_ok=True)
        (dest/'ffprobe.json').write_text(json.dumps(meta,indent=2))
        cue_manifest={'test_only':True,'sample_rate':48000,'total_samples':sample_count,'stems':['synthetic wind','synthetic test footsteps'],'voice':'MISSING_NOT_SIMULATED','music':'NOT_PRESENT','text':caption,'shot_intervals':pack['shots']}
        (dest/'fixture-timeline.json').write_text(json.dumps(cue_manifest,ensure_ascii=False,indent=2))
        outputs={p.name:file_sha(p) for p in dest.iterdir() if p.is_file() and p.name!='receipt.json'}
        result={'status':'TECH_PASS_FIXTURE_ONLY','key':key,'config':config,'outputs':outputs,'video':str(final.relative_to(root)),'frames':frames,'duration_seconds':frames/24,'audio_samples':sample_count,'source_audio_peak':peak,'source_audio_rms':math.sqrt(energy/sample_count),'full_decode':True,'black_freeze_check':'PASS','human_review':{'silent_visual':'NOT_PERFORMED','audio_only':'NOT_PERFORMED','continuity':'NOT_PERFORMED','beginner_comprehension':'NOT_PERFORMED'},'voice':'ABSENT','artistic_scene_complete':False,'generation_requests':0,'external_charge_usd':0,'cache_hit':False}
        receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        for p in dest.iterdir():
            if p.is_file():p.chmod(0o600)
        return dict(result,receipt=str(receipt.relative_to(root)))
