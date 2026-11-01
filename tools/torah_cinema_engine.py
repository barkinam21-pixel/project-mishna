#!/usr/bin/env python3
"""Reusable zero-spend illustrated-film renderer for Mishnah and later Torah series.

All inputs are existing LOCAL artwork. DRY RUN by default. No internet, no
AI image synthesis, no cloud sound synthesis, no secret handling or uploading.
This is a PRIVATE editorial/visual proof renderer, not a film release pipeline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import wave
import unicodedata

# Keep contract validation stdlib-only on CI; media dependencies are optional
# until --render is explicitly requested. No installation or paid calls in CI.
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    cv2 = None
    np = None
    Image = ImageDraw = ImageFont = None

FPS=24
RATE=48000
W=1280
H=720
HEBREW_SERIF='/usr/share/fonts/truetype/noto/NotoSerifHebrew-Regular.ttf'
HEBREW_SANS='/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf'
FORBIDDEN_KEYS={'fal_key','token','api_key','private_key','signed_url'}


def digest(path:Path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()


def validate_manifest(doc:dict, *,require_assets:bool=False):
 errors=[]
 if doc.get('schema_version')!=1:errors.append('schema_version must be 1')
 p=doc.get('policy',{})
 if not isinstance(p,dict):p={};errors.append('policy must be object')
 for k in ('paid_requests_enabled','new_image_generation_enabled','publication_enabled'):
  if p.get(k) is not False:errors.append(f'{k} must be explicitly false')
 if p.get('private_media_only') is not True:errors.append('private_media_only must be true')
 tech=doc.get('render',{})
 if not isinstance(tech,dict):tech={};errors.append('render must be object')
 if tech.get('fps')!=FPS or tech.get('sample_rate')!=RATE:errors.append('must be 24fps 48kHz')
 fac=tech.get('camera_speed_vs_v10')
 if not isinstance(fac,(int,float)) or not math.isfinite(fac) or fac<=0 or fac>2:errors.append('invalid camera speed factor')
 if tech.get('frame_size')!=[W,H]:errors.append('requires 1280x720 frame size')
 assets=doc.get('assets',{})
 if not isinstance(assets,dict) or not assets:errors.append('assets must be a nonempty object');assets={}
 for asset_id,v in assets.items():
  if not isinstance(v,dict):errors.append('invalid asset '+str(asset_id));continue
  if not isinstance(v.get('path'),str) or not v.get('path'):errors.append('asset missing local path '+asset_id)
  elif '://' in v['path']:errors.append('remote image prohibited '+asset_id)
  if v.get('private') is not True:errors.append('asset must be private '+asset_id)
  h=v.get('sha256')
  if not isinstance(h,str) or len(h)!=64 or any(ch not in '0123456789abcdef' for ch in h):errors.append('asset sha256 missing '+asset_id)
  if require_assets and not errors:
   q=Path(v['path'])
   if not q.is_file() or digest(q)!=h:errors.append('asset absent or digest mismatch '+asset_id)
 shots=doc.get('shots',[])
 if not isinstance(shots,list) or not shots:errors.append('shots missing');shots=[]
 next_start=0; seen=set();used={}
 for i,s in enumerate(shots):
  if not isinstance(s,dict):errors.append(f'shot {i} not object');continue
  sid=s.get('id');start=s.get('start_frame');end=s.get('end_frame')
  if sid in seen or not isinstance(sid,str) or not sid:errors.append('duplicate or missing shot ID')
  seen.add(sid)
  if not isinstance(start,int) or not isinstance(end,int) or start!=next_start or end<=start:errors.append('frame gap/overlap/invalid shot '+str(sid))
  if isinstance(end,int):next_start=end
  aid=s.get('asset_id')
  if aid not in assets:errors.append('missing asset source for '+str(sid))
  used[aid]=used.get(aid,0)+1
  if s.get('motion') not in ('locked','push','track','close','reveal','title'):errors.append('unknown camera motion '+str(sid))
  if s.get('source_status') not in ('dramatization','source_paraphrase','visual_metaphor','unverified_reconstruction'):errors.append('source-status missing '+str(sid))
  lines=s.get('lines',[])
  if not isinstance(lines,list) or not (1<=len(lines)<=2):errors.append('subtitle lines 1-2 required '+str(sid))
  else:
   for line in lines:
    if not isinstance(line,str) or len(line)>72:errors.append('invalid long line '+str(sid));continue
    if unicodedata.normalize('NFC',line)!=line:errors.append('line not NFC '+str(sid))
    if any(ord(c) in list(range(0x202a,0x202f))+[0xfffd] for c in line):errors.append('bidi control in '+str(sid))
  if s.get('asset_is_new_original') is True:errors.append('cannot claim existing painting as newly generated '+str(sid))
 if shots and shots[-1].get('end_frame',0)!=doc.get('duration_frames'):errors.append('duration_frames does not match shots')
 if doc.get('duration_frames',0)>FPS*180:errors.append('preview over 180 seconds')
 # Prevent voice/music/foley that contradicts a scene, and never accept secrets.
 audio_design=doc.get('audio_design',{})
 if not isinstance(audio_design,dict):errors.append('audio_design must be an object');audio_design={}
 footfalls=audio_design.get('footsteps_seconds',[])
 if not isinstance(footfalls,list):errors.append('footsteps_seconds must be a list');footfalls=[]
 for sec in footfalls:
  if not isinstance(sec,(int,float)) or not math.isfinite(sec) or sec<0 or sec>next_start/FPS:
   errors.append('footstep timestamp outside movie')
 def scan_keys(value):
  if isinstance(value,dict):
   for k,v in value.items():
    if str(k).lower() in FORBIDDEN_KEYS:errors.append('secrets forbidden in film manifest')
    scan_keys(v)
  elif isinstance(value,list):
   for v in value:scan_keys(v)
 scan_keys(doc)
 if any(k in str(doc).lower() for k in ('sk-proj-','data:image/png;base64','-----begin private key-----')):errors.append('contains credential or embedded image')
 if errors:raise ValueError('; '.join(dict.fromkeys(errors)))
 return {'ok':True,'duration_frames':next_start,'duration_seconds':next_start/FPS,'shots':len(shots),'source_assets':len(assets),'reused_asset_ids':[k for k,n in used.items() if n>1],'no_external_spend':True,'not_final_film':True}


def art_image(path):
 im=cv2.imread(str(path),cv2.IMREAD_COLOR)
 if im is None:raise ValueError('image unreadable')
 ratio=max(W/im.shape[1],H/im.shape[0]);nw=round(im.shape[1]*ratio);nh=round(im.shape[0]*ratio)
 r=cv2.resize(im,(nw,nh),interpolation=cv2.INTER_CUBIC)
 x=(nw-W)//2;y=(nh-H)//2
 return r[y:y+H,x:x+W]


def typography(lines,tag,motion):
 canvas=Image.new('RGBA',(W,H),(0,0,0,0))
 d=ImageDraw.Draw(canvas,'RGBA');title=motion=='title'
 small=ImageFont.truetype(HEBREW_SANS,19)
 if title:
  d.rounded_rectangle((190,218,1090,499),radius=20,fill=(7,13,26,174))
  d.line((370,243,910,243),fill=(211,168,104,195),width=2)
  fonts=[ImageFont.truetype(HEBREW_SERIF,51),ImageFont.truetype(HEBREW_SERIF,38)]
  for i,line in enumerate(lines):
   d.text((W//2,316+i*86),line,font=fonts[min(i,1)],fill=(245,228,201,245),anchor='mm',direction='rtl')
 else:
  y=H-123 if len(lines)==1 else H-150
  d.rounded_rectangle((112,y-17,1168,y+43+42*(len(lines)-1)),radius=12,fill=(8,13,24,173))
  f=ImageFont.truetype(HEBREW_SANS,40 if len(lines)==1 else 36)
  for i,line in enumerate(lines):
   d.text((W//2,y+i*42+8),line,font=f,fill=(247,240,222,245),anchor='mm',direction='rtl',stroke_width=1,stroke_fill=(3,7,16,170))
 if tag:
  d.rounded_rectangle((62,55,565,95),radius=6,fill=(5,10,19,145))
  d.text((538,75),tag,font=small,anchor='rm',direction='rtl',fill=(240,218,175,220))
 return np.asarray(canvas)


def move(im,s,frame,speed):
 p=(frame-s['start_frame'])/max(1,s['end_frame']-s['start_frame']-1)
 mode=s['motion']
 if mode=='locked':z=1.015;dx=dy=0
 elif mode=='push':z=1.012+.027*speed*p;dx=4*p*speed;dy=0
 elif mode=='track':z=1.012+.020*speed*p;dx=-13*p*speed;dy=p
 elif mode=='close':z=1.165+.027*speed*p;dx=168+5*p;dy=16
 elif mode=='reveal':z=1.055-.020*speed*p;dx=5*p;dy=0
 else:z=1.075+.008*speed*p;dx=-7*p;dy=2*p
 cx=390 if mode=='close' else (W-1)/2
 cy=360 if mode=='close' else (H-1)/2
 m=np.array([[z,0,cx*(1-z)+dx],[0,z,cy*(1-z)+dy]],dtype=np.float32)
 return cv2.warpAffine(im,m,(W,H),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)


def soundscape(out_path,nframes,seed=20261101,footsteps_seconds=()):
 """Synthetic copyright-clear score, not a soundtrack master or replacement for actors."""
 from scipy.signal import butter,sosfilt
 n=int(nframes*RATE/FPS);tt=np.arange(n)/RATE
 rng=np.random.default_rng(seed)
 mix=np.zeros(n,dtype=np.float64)
 for hz,mul,phase in [(110,.017,0),(164.81,.008,1.3),(220,.008,.8),(261.63,.005,2.2)]:
  mix+=mul*(np.sin(2*np.pi*hz*tt+phase)+.20*np.sin(2*np.pi*2*hz*tt+phase*1.3))
 mix*=.48+.4*(np.sin(.1*2*np.pi*tt)**2)
 wind=sosfilt(butter(2,290,fs=RATE,output='sos'),rng.normal(0,1,n));wind/=max(1e-9,np.std(wind))
 mix+=.015*wind*(.5+.2*np.sin(tt*.53)**2)
 duration=n/RATE
 # A small original harmonic texture, scales automatically to running time.
 for at,freq in [(duration*q, hz) for q,hz in [(.05,329.63),(.18,261.63),(.29,246.94),(.40,220),(.59,261.63),(.70,329.63),(.85,440)]]:
  start=int(at*RATE);length=min(int(2.4*RATE),n-start);q=np.arange(length)/RATE
  env=(1-np.exp(-20*q))*np.exp(-2.5*q)
  mix[start:start+length]+=.03*env*(np.sin(2*np.pi*freq*q)+.26*np.sin(2*np.pi*freq*2*q))
 # Footfall details, as a built-in optional sequence marker instead of copyrighted samples
 for at in footsteps_seconds:
  o=int(at*RATE);length=min(int(.26*RATE),n-o)
  if length<=0:continue
  q=np.arange(length)/RATE
  tone=sosfilt(butter(2,200,fs=RATE,output='sos'),rng.normal(0,1,length));tone/=max(1e-9,np.std(tone))
  mix[o:o+length]+=.045*(1-np.exp(-130*q))*np.exp(-28*q)*tone
 fade=np.clip(np.minimum(tt/.8,(duration-tt)/1),0,1)
 left=mix*(.985+.015*np.sin(2*np.pi*.17*tt))*fade
 right=mix*(.985+.015*np.sin(2*np.pi*.17*tt+1.3))*fade
 audio=np.stack([left,right],axis=1)
 with wave.open(str(out_path),'wb') as a:
  a.setnchannels(2);a.setsampwidth(2);a.setframerate(RATE)
  a.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
 return {'written':True,'sample_rate':RATE,'samples_per_channel':n,'voice_generated':False}


def tstamp(frames):
 ms=int(round(frames*1000/FPS));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000)
 return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'


def subtitles(shots,filename):
 lines=[]
 for i,s in enumerate(shots,1):
  lines.extend([str(i),f"{tstamp(s['start_frame'])} --> {tstamp(s['end_frame'])}",*s['lines'],''])
 filename.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def render(doc,out_dir):
 if cv2 is None or np is None or Image is None:
  raise RuntimeError('Local renderer requires opencv-python, numpy and pillow')
 audit=validate_manifest(doc,require_assets=True)
 out_dir.mkdir(parents=True,exist_ok=True)
 images={k:art_image(Path(v['path'])) for k,v in doc['assets'].items()}
 shots=doc['shots'];cards={s['id']:typography(s['lines'],s.get('tag',''),s['motion']) for s in shots}
 wav=out_dir/'original_private_soundbed.wav';sound=soundscape(wav,doc['duration_frames'],footsteps_seconds=doc.get('audio_design',{}).get('footsteps_seconds',[]))
 raw=out_dir/'private_motion_proof_pre_master.mp4';out=out_dir/'private_cinematic_proof.mp4'
 proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','bgr24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0','-i',str(wav),'-map','0:v','-map','1:a','-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-r',str(FPS),'-g','48','-movflags','+faststart','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','aac','-b:a','160k','-ar','48000','-ac','2','-metadata:s:a:0','language=heb',str(raw)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 last=None
 for s in shots:
  src=images[s['asset_id']];card=cards[s['id']]
  for i in range(s['start_frame'],s['end_frame']):
   frame=move(src,s,i,doc['render']['camera_speed_vs_v10'])
   if s['motion']=='title':frame=(frame.astype(np.float32)*.6+np.array([13,15,18],dtype=np.float32)*.4).astype('uint8')
   p=(i-s['start_frame'])/(s['end_frame']-s['start_frame'])
   opacity=min(1,p*FPS/.40,(1-p)*(s['end_frame']-s['start_frame'])/FPS/.65)
   alpha=card[:,:,3:4].astype('float32')/255*opacity
   frame=(frame.astype('float32')*(1-alpha)+card[:,:,:3][:,:,::-1].astype('float32')*alpha).astype('uint8')
   if s.get('crossfade_from_previous') and last is not None and i-s['start_frame']<9:
    q=(i-s['start_frame']+1)/10
    frame=cv2.addWeighted(last,1-q,frame,q,0)
   frame[:37,:]=(frame[:37,:]*.22).astype('uint8');frame[-37:,:]=(frame[-37:,:]*.22).astype('uint8')
   if i==s['end_frame']-1:last=frame.copy()
   proc.stdin.write(frame.tobytes())
 proc.stdin.close();stderr=proc.stderr.read().decode();code=proc.wait()
 if code:raise RuntimeError('encode failed: '+stderr[-2000:])
 # Audio measured and remastered for comfortable mobile playback; no fake voice added.
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(raw),'-map','0:v:0','-map','0:a:0','-c:v','copy','-af','loudnorm=I=-20:TP=-4:LRA=7','-c:a','aac','-b:a','160k','-ar','48000','-ac','2','-movflags','+faststart','-metadata:s:a:0','language=heb',str(out)],check=True)
 subtitles(shots,out_dir/'private_cinematic_proof.srt')
 report={'status':'PRIVATE_EDITING_PROOF_NOT_A_RELEASE','project_family':doc.get('franchise','torah-film-studio'),'episode':doc.get('episode'),'video_sha256':digest(out),'source_art_sha256':{k:v['sha256'] for k,v in doc['assets'].items()},'camera_speed_factor':doc['render']['camera_speed_vs_v10'],'render_frames':doc['duration_frames'],'duration_seconds':doc['duration_frames']/FPS,'audio':sound,'new_ai_images':0,'new_ai_voice':0,'paid_requests':0,'workspace_usage':'unknown','rights_and_history_pending':True,'limitations':doc.get('limitations',[])}
 (out_dir/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return out,report


def main():
 a=argparse.ArgumentParser();a.add_argument('manifest',type=Path);a.add_argument('--render',action='store_true',help='Explicitly render locally; no cloud spending');a.add_argument('--out-dir',type=Path,default=Path('local-output/private-cinema-preview'));opts=a.parse_args()
 manifest=json.loads(opts.manifest.read_text(encoding='utf8'))
 audit=validate_manifest(manifest,require_assets=opts.render)
 if not opts.render:print(json.dumps({'mode':'dry_run','audit':audit},ensure_ascii=False,indent=2));return
 path,report=render(manifest,opts.out_dir)
 print(json.dumps({'video':str(path),'sha256':report['video_sha256'],'fps':FPS,'frames':report['render_frames']},ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(type(exc).__name__+': '+str(exc),file=sys.stderr);sys.exit(2)