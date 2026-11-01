#!/usr/bin/env python3
"""Deterministic SYNTHETIC audio-mood study for the first cinematic prologue.

No external samples / compositions, no TTS, no network, no licensed soundfonts.
Not a final film score, not original acoustic Foley and not speech.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt
import soundfile as sf

FS=48000
DURATION=45
N=FS*DURATION
RNG=np.random.default_rng(20261101)


def ease(t,attack=0.8,release=0.7):
    t=np.asarray(t)
    return np.clip(t/attack,0,1)**1.6*np.clip((t.max()-t)/release,0,1)**1.6


def note(dst,start,dur,hz,volume,kind="string",attack=0.8,release=1.4):
    n=int(dur*FS); idx=int(start*FS)
    if idx>=len(dst):return
    n=min(n,len(dst)-idx)
    t=np.arange(n,dtype=np.float64)/FS
    fade=np.clip(t/attack,0,1)**1.5 * np.clip((dur-t)/release,0,1)**1.1
    if kind=="string":
        vibrato=.0015*np.sin(2*np.pi*4.5*t)
        phase=2*np.pi*hz*(t+(0.0015/(2*np.pi*4.5))*np.sin(2*np.pi*4.5*t))
        sig=(.68*np.sin(phase)+.24*np.sin(2*phase+.4)+.12*np.sin(3*phase+1.1)+.07*np.sin(4*phase+1.3))
    elif kind=="bell":
        phase=2*np.pi*hz*t
        sig=.76*np.sin(phase)+.14*np.sin(2*phase+.2)+.08*np.sin(3*phase+1.0)
        fade*=np.exp(-t/3.5)
    else:
        phase=2*np.pi*hz*t
        sig=np.sin(phase)
    dst[idx:idx+n]+=(sig*fade*volume).astype(np.float32)


def mix():
    L=np.zeros(N,dtype=np.float32)
    R=np.zeros(N,dtype=np.float32)
    # An original, synthesized dry wind bed using filtered seeded noise (not an outside recording).
    raw=RNG.normal(size=N).astype(np.float32)
    band=sosfilt(butter(3,[90,1200],btype="bandpass",fs=FS,output="sos"),raw).astype(np.float32)
    clock=np.arange(N,dtype=np.float32)/FS
    gust=(.30+.14*np.sin(2*np.pi*.075*clock)**2+.045*np.sin(2*np.pi*.17*clock))
    ambience=band*gust*.050
    L+=ambience;R+=.87*ambience
    # Sparse synthesized gravel contacts early only (avoid arbitrary 45s loop).
    for k,when in enumerate((0.58,1.57,2.77,3.72,5.0,6.06,7.58,8.47,9.73,10.54)):
        count=int(.22*FS)
        t=np.arange(count,dtype=np.float32)/FS
        crackle=RNG.normal(size=count).astype(np.float32)
        crackle=sosfilt(butter(2,[250,3800],btype="bandpass",fs=FS,output="sos"),crackle)
        shape=np.exp(-t*25)*(1+0.14*np.sin(2*np.pi*65*t))
        pulse=(crackle*shape*.07).astype(np.float32)
        start=int(when*FS)
        if k%2==0:
            L[start:start+count]+=pulse;R[start:start+count]+=.6*pulse
        else:
            L[start:start+count]+=.7*pulse;R[start:start+count]+=pulse
    # The first 30s deliberately contain no "epic" soundtrack, creating space for dialogue.
    # A short original, unlicensed-to-anyone-else-by-dependency, four-note transmission motif begins at contact.
    melody=[(30.0,2.2,293.6648,.041),(32.4,1.8,349.2282,.039),(34.0,2.2,440.0,.043),(36.3,2.2,391.9954,.039),
            (39.0,2.5,349.2282,.040),(41.3,3.2,293.6648,.045)]
    for j,(when,dur,hz,amp) in enumerate(melody):
        note(L,when,dur,hz,amp,kind="bell",attack=.25,release=.55)
        note(R,when+.015,dur,hz*.998,amp*.78,kind="bell",attack=.24,release=.6)
    # Low sustained harmonic body, no artificial choir and no sourced copyrighted theme.
    chords=[(30,5.0,[146.8324,220.0,293.6648]),(35.0,5.0,[116.5409,174.614,293.6648]),(40.0,5.0,[130.8128,196.0,349.2282])]
    for start,dur,hzs in chords:
        for j,h in enumerate(hzs):
            note(L,start,dur,h*.999, .019,attack=1.7,release=1.3)
            note(R,start+.03,dur,h*1.0007,.020,attack=1.7,release=1.3)
    # Gentle stereo space using independent taps; strictly no copyrighted convolution impulses.
    for out in (L,R):
        for ms,gain in ((53,.11),(137,.075),(257,.045)):
            off=int(FS*ms/1000)
            out[off:]+=out[:-off].copy()*gain
    # 1.4s closing fade, normalize preview loudness without clipping.
    endfade=np.minimum(1.0,(DURATION-clock)/1.4).clip(0,1)
    L*=endfade;R*=endfade
    audio=np.stack([L,R],axis=1)
    peak=np.max(np.abs(audio))
    audio=audio/peak*0.65 if peak else audio
    return audio.astype(np.float32)


def main():
    dest=Path(__file__).resolve().parents[1]/"audio_private"
    dest.mkdir(parents=True,exist_ok=True)
    a=mix()
    wav=dest/"original_opening_foley_and_motif_draft_45s.wav"
    sf.write(wav,a,FS,subtype="PCM_16")
    report={"sample_rate_hz":FS,"channels":2,"duration_seconds":DURATION,"samples_per_channel":N,
            "status":"audio_only_synthetic_draft_no_dialogue_not_final_score",
            "composition":"algorithmically constructed new sketch; no outside film recordings, downloaded samples, voices, or soundfonts",
            "rights_review":"only local generated tones/wind/gravel synthesis; final score requires compositional and user review",
            "paid_external_requests":0,"imagegen_requests":0,"dialogue_present":False,
            "music_present_before_30_seconds":False,"motif_start_seconds":30,"peak_amplitude":float(np.max(np.abs(a)))}
    (dest/"audio_study_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(wav)
    print(json.dumps(report,indent=2))

if __name__=="__main__":main()