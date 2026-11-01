#!/usr/bin/env python3
"""Private editorial movement BLOCKOUT for OPN01..OPN07; procedural staging only.

No AI generation, no external requests, no copyrighted footage. This deliberately
uses simplified silhouettes; it is not a finished illustration or historical evidence.
"""
import argparse, hashlib, json, math, subprocess, sys
from pathlib import Path

import cv2
import numpy as np

FPS, W, H = 24, 960, 540
SKY_TOP=(42,40,37) # BGR
SKY_BOTTOM=(106,112,128)


def tween(x):
    x = max(0.0,min(1.0,x));return x*x*(3-2*x)


def circle(im,x,y,r,col): cv2.circle(im,(int(x),int(y)),max(1,int(r)),col,-1,cv2.LINE_AA)
def poly(im,points,col): cv2.fillPoly(im,[np.array(points,np.int32)],col,cv2.LINE_AA)
def line(im,p,q,col,t=2): cv2.line(im,tuple(map(int,p)),tuple(map(int,q)),col,int(t),cv2.LINE_AA)


def build_sky(frame_i, sid, t):
    # Grounded graphic blockout, not final backgrounds. Muted warm rim light screen-left.
    y=np.linspace(0,1,H).reshape(-1,1,1)
    top=np.array(SKY_TOP,np.float32).reshape(1,1,3)
    bottom=np.array(SKY_BOTTOM,np.float32).reshape(1,1,3)
    a=np.clip((y*1.35),0,1)
    col=top*(1-a)+bottom*a
    im=np.broadcast_to(col,(H,W,3)).copy().astype(np.uint8)
    # dawn expands near screen LEFT when time passes; very subtle.
    xx=np.linspace(0,1,W).reshape(1,-1)
    yy=np.linspace(0,1,H).reshape(-1,1)
    glow=np.exp(-((xx-0.15)**2/0.085+(yy-0.41)**2/0.025))*((0.38 if sid!='OPN07' else 0.63)+0.08*t)
    glow=np.clip(glow,0,1)[:,:,None]
    gold=np.array([102,162,205],np.float32).reshape(1,1,3)
    im=np.clip(im*(1-glow)+gold*glow,0,255).astype(np.uint8)
    # mountains on horizon have fixed geometry; preserve direction and relative scale.
    poly(im,[(0,285),(85,260),(165,286),(272,228),(332,278),(410,257),(501,280),(635,216),(760,263),(900,240),(960,263),(960,540),(0,540)],(83,81,78))
    poly(im,[(0,320),(117,307),(200,321),(358,271),(454,313),(555,291),(675,313),(792,277),(960,301),(960,540),(0,540)],(67,64,64))
    poly(im,[(0,410),(90,382),(202,396),(318,370),(421,397),(557,376),(682,392),(788,367),(960,383),(960,540),(0,540)],(49,52,54))
    # Warm spot along western horizon, no divine rays.
    ellipse_shift = 7*math.sin(t*1.3)
    circle(im,170,284+ellipse_shift,8 if sid != 'OPN07' else 12,(118,171,216))
    # Road as angled graphic shape, not an archaeological claim
    poly(im,[(0,540),(970,540),(685,417),(410,390),(216,396),(0,423)],(69,65,65))
    line(im,(0,423),(216,396),(79,77,81),2)
    for i in range(38):
        x=(i*137+54)%W; py=415+((i*43)%120)
        color=(84,82,79) if i%3 else (97,95,92)
        line(im,(x,py),(x+5+(i%8),py-1),color,1)
    return im


def draw_figure(im,x,ground,scale,role,phase=0.0,walk=0.0,gest=0.0,blink=False,look=0.0):
    # Adult body-weight shift and cloth/arm gestures; no counterfeit lip sync.
    earth=role=='older'
    cloak=(66,89,109) if earth else (97,92,77)  # warmer earth vs slate young, BGR
    cloak_edge=(95,120,145) if earth else (137,119,92)
    skin=(110,149,183) if earth else (118,158,189)
    ink=(32,42,48)
    cyc=math.sin(phase)
    sway=0.9*cyc*walk
    shoulder_y=ground-88*scale+sway
    head_y=ground-112*scale+sway
    cx=x+1.2*cyc*walk
    # leg pair alternates and has explicit knee positions (simplified blockout).
    for k,off in enumerate((0,math.pi)):
        q=math.sin(phase+off)*walk
        hip=(cx+(-8 if k==0 else 8)*scale,ground-41*scale)
        knee=(cx+q*14*scale+(-7 if k==0 else 7)*scale,ground-23*scale)
        foot=(cx+q*22*scale+(-5 if k==0 else 5)*scale,ground-3*scale-max(0,q)*7*scale)
        line(im,hip,knee,ink,max(2,int(11*scale)))
        line(im,knee,foot,ink,max(2,int(8*scale)))
        line(im,foot,(foot[0]+(-9*scale),foot[1]),(39,47,51),max(2,int(6*scale)))
    # Cloak flares in wind and walk; outline left and warm dawn-facing edge.
    poly(im,[(cx-16*scale,shoulder_y),(cx+12*scale,shoulder_y),
             (cx+21*scale+8*cyc*walk,ground-33*scale),
             (cx+16*scale,ground-34*scale),(cx-23*scale,ground-35*scale)],cloak)
    line(im,(cx-16*scale,shoulder_y),(cx-21*scale,ground-35*scale),cloak_edge,max(1,int(2*scale)))
    # Arms: older holds worn water skin, gestures when asked.
    ax = -17 if earth else 14
    base=(cx+ax*scale,shoulder_y+6*scale)
    if gest and earth:
        hand=(cx+(-25-16*gest)*scale,ground-66*scale)
    elif gest and not earth:
        hand=(cx+(12-25*gest)*scale,ground-66*scale)
    else:
        hand=(cx+ax*scale+4*math.sin(phase+1.1)*walk*scale,ground-47*scale)
    line(im,base,hand,cloak_edge,max(2,int(7*scale)))
    circle(im,hand[0],hand[1],4.5*scale,skin)
    # Head and eye line; non-portrait silhouettes, facial features deliberately abstract.
    circle(im,cx,head_y,13.3*scale,skin)
    if earth:
        # Beard reads as older without impersonating a real historical person.
        poly(im,[(cx-9*scale,head_y+8*scale),(cx+8*scale,head_y+8*scale),(cx+2*scale,head_y+19*scale),(cx-2*scale,head_y+17*scale)],(42,55,64))
    eye_y=head_y-(0.5*scale if not blink else -1*scale)
    line(im,(cx-7*scale,eye_y),(cx+2*scale,eye_y+blink*1*scale),(39,55,63),max(1,int(1.5*scale)))
    return (cx,head_y)


def draw_shot(im,sid,f,shot_len):
    p=f/max(1,shot_len-1)
    g=450
    # 3 actual body-pose phases in continuous action, unlike repeated static crops.
    if sid=='OPN01':
        # ankle-level crop, heel strike and swing with an offset gait
        for idx in range(2):
            x=690-idx*300-110*p
            cy=200+idx*23
            sc=2.15 if idx==0 else 1.85
            phase=2*math.pi*(p*2.15)+idx*math.pi
            shift=math.sin(phase)
            line(im,(x,cy),(x-13+shift*24,g-70*sc),(35,44,49),40)
            line(im,(x-13+shift*24,g-70*sc),(x-75+shift*37,g-12*sc-14*max(0,shift)),(43,52,58),30)
            poly(im,[(x-100+shift*37,g-14*sc-14*max(0,shift)),(x-35+shift*37,g-14*sc-14*max(0,shift)),(x-29+shift*37,g-7*sc-14*max(0,shift)),(x-108+shift*37,g-6*sc-14*max(0,shift))],(58,67,71))
        for i in range(13):
            dx=(i*31+f*1.1)%180
            circle(im,540-dx,445-5*i+4*math.sin(f*.05+i),1.4+(i%4)*.4,(104,125,147))
    elif sid in ('OPN02','OPN07'):
        far=sid=='OPN07'
        sc=(0.83 if not far else .62)
        moving=(-78 if not far else -100)*p
        x0=(785 if not far else 590)+moving
        t=f/FPS
        draw_figure(im,x0-40,425,sc,'older',phase=t*6.2,walk=1)
        draw_figure(im,x0+36,428,sc*.98,'young',phase=t*6.2+1.2,walk=1)
        # horizon lines from foreground give a sense of depth without camera shake.
        if far:
            glow=(35+int(p*20))
            cv2.ellipse(im,(170,298),(115,28),0,205,335,(115,150,175),1,cv2.LINE_AA)
    elif sid=='OPN03':
        older_x=380; young_x=586
        walk=max(0,1-2*p)
        draw_figure(im,older_x-12*tween(min(1,p*1.7)),479,1.7,'older',phase=f*.28,walk=walk)
        draw_figure(im,young_x-34*tween(min(1,p*1.8)),484,1.7,'young',phase=f*.30+1.6,walk=walk,gest=tween(max(0,(p-.43)*2)))
    elif sid=='OPN04':
        # Younger OTS as near-frame shape; older centered left in open composition.
        draw_figure(im,400,494,1.9,'older',walk=0,blink=(p>.61 and p<.64))
        # silhouette of young shoulder in foreground to clarify eyeline; not an extra historical figure.
        poly(im,[(740,335),(960,325),(960,540),(690,540),(675,415)],(36,44,50))
        circle(im,809,294,82,(56,63,67))
    elif sid=='OPN05':
        # Close on older man; readable emotional pause via head/eyes, restrained.
        draw_figure(im,510,595,3.15,'older',walk=0,blink=(.42<p<.445))
        # light falls along left cheek, no magic beams or pseudo-prophecy.
        cv2.ellipse(im,(460,240),(85,116),0,96,239,(86,112,141),2,cv2.LINE_AA)
    elif sid=='OPN06':
        # Explicit distinct key poses of two hands passing an ordinary waterskin.
        older_hand_end=np.array((448+70*tween(p),330+4*math.sin(p*math.pi)),float)
        younger_hand_end=np.array((695-110*tween(p),355-3*math.sin(p*math.pi)),float)
        # arms enter from opposite sides; fixed crossing axis.
        line(im,(180,460),older_hand_end,(77,102,121),65)
        line(im,(850,490),younger_hand_end,(104,107,99),60)
        circle(im,*older_hand_end,27,(122,159,191))
        circle(im,*younger_hand_end,27,(132,165,192))
        bag_x=older_hand_end[0]+48-15*tween((p-.55)*2)
        bag_y=older_hand_end[1]+15
        # leather waterskin: no text, no religious/archaeological claims.
        cv2.ellipse(im,(int(bag_x),int(bag_y+42)),(27,41),-13,0,360,(65,89,117),-1,cv2.LINE_AA)
        line(im,(older_hand_end[0],older_hand_end[1]),(bag_x,bag_y+6),(121,134,144),7)
        if p>.58:
            line(im,(younger_hand_end[0],younger_hand_end[1]),(bag_x+14,bag_y+20),(129,141,147),5)
    # letterbox bars and edge vignette; safe 16:9 preview without texts inside artwork.
    im[:22]=np.clip(im[:22]*0.25,0,255).astype(np.uint8)
    im[-22:]=np.clip(im[-22:]*0.25,0,255).astype(np.uint8)
    return im


def make_ass(manifest,filepath):
    # libass correctly shapes right-to-left Hebrew; dialogue is a draft with no human voice.
    h='''[Script Info]\nScriptType: v4.00+\nPlayResX: 960\nPlayResY: 540\nWrapStyle: 0\nScaledBorderAndShadow: yes\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Main,Noto Sans Hebrew,30,&H00F8F8F0,&H00FFFFFF,&HAA101118,&H9C0B1117,0,0,0,0,100,100,0,0,1,2,1,2,90,90,46,1\nStyle: Label,Noto Sans Hebrew,16,&H00E3D9CF,&H00FFFFFF,&H900B1117,&H8A101015,0,0,0,0,100,100,0,0,1,1,0,9,25,25,35,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    def fmt(fr):
        cs=round(fr*100/FPS)
        return f'{cs//360000}:{(cs//6000)%60:02d}:{(cs//100)%60:02d}.{cs%100:02d}'
    lines=[h]
    lines.append(f'Dialogue: 0,{fmt(0)},{fmt(1080)},Label,,0,0,0,,סקיצת תנועה — איורי הפקה טרם נוצרו\n')
    lines.append(f'Dialogue: 1,{fmt(8)},{fmt(78)},Main,,0,0,0,,המחזה סמלית — לא אירוע היסטורי מתועד\n')
    cue=[('OPN03',295,420),('OPN05',574,691),('OPN06',749,847)]
    for sid,start,end in cue:
        s=next(x for x in manifest['shots'] if x['id']==sid)
        assert len(s['dialogue_he'])==1
        text=s['dialogue_he'][0]['text']
        assert len(text)<=48
        lines.append(f'Dialogue: 2,{fmt(start)},{fmt(end)},Main,,0,0,0,,{text}\n')
    lines.append(f'Dialogue: 1,{fmt(942)},{fmt(1068)},Main,,0,0,0,,מה עובר מדור לדור?\n')
    filepath.write_text(''.join(lines),encoding='utf8')


def run(args):
    manifest=json.loads(args.manifest.read_text(encoding='utf8'))
    shots=manifest['shots']
    if [s.get('id') for s in shots] != [f'OPN{i:02d}' for i in range(1,8)]:
        raise ValueError('Only chronological OPN01-OPN07 may be rendered')
    if shots[-1].get('end_frame') != 1080 or sum(s.get('frames',0) for s in shots) != 1080:
        raise ValueError('Exactly 1080 frame-timed planned shots required')
    if any(s.get('asset_status') != 'not_generated' for s in shots):
        raise ValueError('This is a blockout only; real image assets must use another renderer')
    if manifest['privacy'].get('new_external_spend_authorized') is not False or manifest['privacy'].get('generation_in_chatgpt_forbidden') is not True:
        raise ValueError('Strict zero-spend/no-imagegen gate required')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix('.silent.mp4')
    ASS=args.output.with_suffix('.ass')
    make_ass(manifest,ASS)
    proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-c:v','libx264','-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-movflags','+faststart',str(tmp)],stdin=subprocess.PIPE)
    count=0
    for shot in shots:
        length=shot['frames']
        for n in range(length):
            frame=build_sky(count,shot['id'],n/length)
            frame=draw_shot(frame,shot['id'],n,length)
            try:proc.stdin.write(frame.tobytes())
            except BrokenPipeError:raise RuntimeError('FFmpeg lost frame stream')
            count+=1
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError('frame encoder failed')
    assert count==1080
    audio=args.audio
    if not audio.exists():raise FileNotFoundError(audio)
    # Burn accurate Hebrew captions then add source-made, voice-free scratch audio.
    filterpath=str(ASS).replace(':','\\:').replace("'",r"\'")
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(tmp),'-i',str(audio),'-vf',f"ass='{filterpath}'",'-map','0:v:0','-map','1:a:0','-c:v','libx264','-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-t','45','-metadata:s:a:0','language=heb','-movflags','+faststart',str(args.output)]
    subprocess.run(cmd,check=True)
    tmp.unlink(missing_ok=True)
    sha=hashlib.sha256(args.output.read_bytes()).hexdigest()
    report={'status':'PRIVATE_MOTION_BLOCKOUT_NOT_FINISHED_FILM','source_manifest':str(args.manifest),'frames':1080,'fps':24,'duration_sec':45,'size':[W,H],'shots':7,'paid_requests':0,'new_ai_images':0,'original_illustrations_generated':0,'synthetic_figure_blocking':True,'actual_spoken_dialogue':False,'dialogue_is_text_only':True,'sound_source':'original_synthetic_private_45s_draft','publish_authorized':False,'sha256':sha,'video':str(args.output)}
    reportpath=args.output.with_suffix('.qa.json')
    reportpath.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',type=Path,default=Path('episodes/berakhot-01-01/opening-45s-director-pack-v1.json'))
    p.add_argument('--audio',type=Path,required=True,help='Path to PRIVATE original draft audio; never commit media to public GitHub')
    p.add_argument('--output',type=Path,required=True,help='Private output MP4 path')
    run(p.parse_args())