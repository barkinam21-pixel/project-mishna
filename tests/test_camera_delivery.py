import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from PIL import Image
from tools import private_subpixel_camera_v2 as camera
from tools import private_proof_assembler as proof

class CameraDeliveryTests(unittest.TestCase):
    def test_fractional_sampler_moves_pixels_without_black_edges(self):
        im=Image.new('RGB',(320,180))
        im.putdata([(20+x%210,30+y%180,70) for y in range(180) for x in range(320)])
        p=dict(width=160,height=90,frames=24,zoom_start=1.06,zoom_end=1.12,drift_x=.01,drift_y=0)
        first=camera.sample_frame(im,p,0)
        last=camera.sample_frame(im,p,23)
        self.assertNotEqual(first.tobytes(),last.tobytes())
        self.assertGreater(min(last.tobytes()),0)
        with self.assertRaises(ValueError):
            camera.sample_frame(im,{**p,'drift_x':.5},23)

    def test_existing_encoder_uses_prepared_camera_sequence(self):
        cfg={'images':[{'shot_id':'x','path':'x.png'}], 'voice_takes':[], 'intentional_silence':True}
        plan={'shots':[{'id':'x','duration_frames':24}], 'target_duration_frames':24}
        args=proof.ffmpeg_args(cfg,plan,Path('/tmp'),Path('/tmp'),camera_inputs={'x':'camera-x/%06d.png'})
        self.assertIn('camera-x/%06d.png',args)
        self.assertNotIn('-loop',args)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable: encoded motion not run")
    def test_encoded_motion_is_present_in_output_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            im=Image.new('RGB',(320,180))
            im.putdata([(30+x%190,40+y%160,90) for y in range(180) for x in range(320)])
            im.save(folder/'original.png')
            plan=dict(width=160,height=90,frames=12,zoom_start=1.06,zoom_end=1.14,drift_x=0,drift_y=0)
            pattern=camera.prepare_sequence(folder/'original.png',plan,folder/'frames')
            subprocess.run(['ffmpeg','-v','error','-framerate','24','-i',pattern,'-c:v','libx264','-pix_fmt','yuv420p',str(folder/'out.mp4')],check=True,capture_output=True)
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(folder/'out.mp4'),'-f','rawvideo','-pix_fmt','rgb24','-'])
            size=160*90*3
            self.assertEqual(len(raw),12*size)
            self.assertNotEqual(raw[:size],raw[-size:])
            self.assertGreater(sum(abs(a-b) for a,b in zip(raw[:size],raw[-size:]))/size,1)

    def test_multiple_caption_phrases_per_shot_are_accepted_without_approval(self):
        import copy
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            draft=json.loads((proof.ROOT/'episodes/berakhot-01-01/private-proof-caption-draft.json').read_text())
            first=draft['cues'][0]
            a,b=copy.deepcopy(first),copy.deepcopy(first)
            middle=(a['start_frame']+a['end_frame'])//2
            a['end_frame']=middle
            b['start_frame']=middle
            b['id']+='-part2'
            draft['cues'][:1]=[a,b]
            (root/'captions.json').write_text(json.dumps(draft))
            config=json.loads(proof.EXAMPLE.read_text())
            config['caption_master']='captions.json'
            result=proof.audit(config,json.loads(proof.BLUEPRINT.read_text()),root)
            self.assertNotEqual(result['status'],'INVALID',result)
            self.assertFalse(draft['caption_text_approved'])
            b['start_frame']+=1
            (root/'captions.json').write_text(json.dumps(draft))
            self.assertEqual(proof.audit(config,json.loads(proof.BLUEPRINT.read_text()),root)['status'],'INVALID')

    def test_non_widescreen_source_fills_frame_without_distortion(self):
        im=Image.new('RGB',(240,180),(90,80,70))
        p=dict(width=160,height=90,frames=24,zoom_start=1.02,zoom_end=1.06,drift_x=0,drift_y=0)
        frame=camera.sample_frame(im,p,23)
        self.assertEqual(frame.getpixel((0,0)),(90,80,70))
        matrix=camera.transform_at(1,240,180,p)
        self.assertEqual(matrix[0][0],matrix[1][1])

    def test_rejected_hebrew_recording_cannot_return_as_real_voice(self):
        cfg=json.loads(proof.EXAMPLE.read_text())
        cfg['voice_takes']=[dict(id='bad',path='missing.wav',start_frame=0,end_frame=1800,
            sha256='4bb174c581f2c2d8d59b8fee1792d552e676e276154499734bc52dc4027ccb3b')]
        report=proof.audit(cfg,json.loads(proof.BLUEPRINT.read_text()),proof.ROOT)
        self.assertTrue(any('rejected by human listening' in e for e in report['errors']))
