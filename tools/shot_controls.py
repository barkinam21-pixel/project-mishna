"""Structured shot direction and deterministic QA; semantic checks never fabricated."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

FIELDS='shot_id scene_id purpose narrative_role characters_present character_priority environment time_of_day mood camera_distance camera_angle lens_feel composition_notes continuity_requirements lighting_notes gesture_notes eye_line_notes forbidden_elements style_lock reference_images reference_roles output_aspect_ratio generation_parameters review_status subject_hierarchy focal_action must_be_in_frame must_not_dominate_frame left_right_placement depth_plan motion_implication cut_motivation emotional_beat new_relative_to_previous'.split()
FLAGS='preserve_character_identity preserve_costumes preserve_environment_style preserve_color_script avoid_childlike_look avoid_text_in_image avoid_extra_limbs_or_fingers avoid_face_distortion avoid_reference_copy_too_closely'.split()
EDITABLE={'composition_notes','camera_distance','camera_angle','lens_feel','continuity_requirements','prompt_text','generation_parameters','subject_hierarchy','focal_action','must_be_in_frame','must_not_dominate_frame','depth_plan','motion_implication','new_relative_to_previous'}


def validate(d, shot, manifest):
    errors=['Missing director field: '+f for f in FIELDS if f not in d or d[f] in ('',None,[],{})]
    errors += ['Missing boolean: '+f for f in FLAGS if type(d.get(f)) is not bool]
    if errors: return errors
    if d['shot_id']!=shot['id'] or d['scene_id']!=manifest['scene']: errors.append('Director shot/scene mismatch')
    if d['characters_present']!=shot['characters']: errors.append('Character continuity mismatch')
    if d['time_of_day']!='sunset' or d['output_aspect_ratio']!='16:9': errors.append('Opening time/aspect lock mismatch')
    if any(d[f] is not True for f in FLAGS): errors.append('Opening continuity/safety lock disabled')
    lock={'style':manifest['style'],'characters':manifest['characters'],'references':manifest['references']}
    expected=hashlib.sha256(json.dumps(lock,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if d['style_lock']!=expected: errors.append('Style lock changed')
    if d['reference_images']!=[r['sha256'] for r in manifest['references']]: errors.append('Director references mismatch')
    if d['reference_roles']!=[r['role'] for r in manifest['references']]: errors.append('Reference role mismatch')
    if d['review_status']!='PENDING_HUMAN': errors.append('Director cannot grant approval')
    if d['generation_parameters']!={'guidance':1.0,'steps':4}: errors.append('Unsupported generation parameters')
    return errors


def apply_override(manifest, shot_id, change):
    if set(change)-EDITABLE: raise ValueError('Forbidden override field')
    result=copy.deepcopy(manifest); shot=next(s for s in result['shots'] if s['id']==shot_id)
    for k,v in change.items():
        if k=='prompt_text': shot['prompt']=v
        else: shot['director'][k]=v
    errors=validate(shot['director'],shot,result)
    if errors: raise ValueError('; '.join(errors))
    return result


def visual_qa(path, references):
    flags=[]
    with Image.open(path) as image:
        image.load(); sample=image.convert('RGB').resize((64,36))
        for ref in references:
            with Image.open(ref) as original:
                delta=ImageStat.Stat(ImageChops.difference(sample,original.convert('RGB').resize(sample.size))).mean
                if sum(delta)/3 < 18: flags.append('REFERENCE_COMPOSITION_SIMILARITY_REVIEW')
    semantic=['people_count','adult_ages','costumes','hands_faces_anatomy','unwanted_text','lighting','character_identity','wide_original_composition']
    return {'deterministic_status':'FLAG' if flags else 'PASS','flags':flags,
            'method':'64x36 RGB mean absolute difference <18; heuristic only',
            'semantic':{k:'NOT_EVALUATED' for k in semantic},'human_review_required':True}


def main():
    from tools.comfy_scene_images import run,under,atomic
    from tools.cloudflare_image_backend import CloudflareClient
    p=argparse.ArgumentParser();p.add_argument('command',choices=['validate_shot','generate_shot','review_shot'])
    p.add_argument('--shot',required=True);p.add_argument('--manifest',default='episodes/berakhot-01-01/comfy-opening-images.json')
    p.add_argument('--root',default='.');p.add_argument('--out',default='private-media/director-images');p.add_argument('--override');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args();root=Path(a.root).resolve();m=json.loads(under(root,a.manifest).read_text())
    if a.override:m=apply_override(m,a.shot,json.loads(under(root,a.override).read_text()))
    m['shots']=[s for s in m['shots'] if s['id']==a.shot]
    if not m['shots']:p.error('Unknown shot')
    m['backend']=m['available_backends']['cloudflare']
    if a.command=='review_shot':
        report=json.loads(under(root,a.out+'/report.json').read_text())
    else:
        generate=a.command=='generate_shot' and not a.dry_run
        if generate:
            cached=run(m,root,under(root,a.out),None,False)
            if cached['shots'][0]['status'] in ('CANDIDATE','ACCEPTED'):
                print(json.dumps(cached,ensure_ascii=False,indent=2));return
            # Existing authorization is not upgraded by selecting a provider.
            m['authorization']['zero_cost_compute_verified']=False
            c=CloudflareClient(m['backend'])
            from tools.comfy_scene_images import specifications
            rows=specifications(m,root)
            if rows[0]['missing']: raise ValueError('Preflight failed')
            try:
                c.readiness(rows[0]['spec'])
            except Exception as error:
                import datetime
                atomic(under(root,a.out+'/last-error.json'),{'status':'BLOCKED_BEFORE_INFERENCE',
                    'code':str(error) if type(error).__name__=='CloudflareBlocked' else type(error).__name__,
                    'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'submissions':0})
                raise
            m['authorization']['zero_cost_compute_verified']=True
            m['authorization']['component_licenses_verified']=m['backend']['safety']['licenses_verified']
        report=run(m,root,under(root,a.out),CloudflareClient(m['backend']) if generate else None,generate)
        report['live_readiness']='NOT_CHECKED' if not generate else 'CHECKED_BEFORE_SUBMISSION'
        atomic(under(root,a.out+'/report.json'),report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,TimeoutError) as error:
        import sys
        code=str(error) if type(error).__name__=='CloudflareBlocked' else type(error).__name__
        print(json.dumps({'status':'BLOCKED','code':code,'next':'Inspect private state; no automatic resubmission'}));sys.exit(2)


def assess_composition(path, measurement):
    """Validate explicit human bounding-box observations, never infer them from pixels."""
    from tools.comfy_scene_images import sha
    if measurement.get('image_sha256')!=sha(path) or not measurement.get('reviewer'):
        raise ValueError('Composition measurements must identify image and reviewer')
    if measurement.get('method')!='human_bounding_boxes':raise ValueError('Unsupported measurement method')
    with Image.open(path) as im:width,height=im.size
    boxes=measurement.get('boxes',[])
    if len(boxes)!=2 or {b.get('character') for b in boxes}!={'A','B'}:raise ValueError('Two identified adult character boxes required')
    flags=[];ratios={}
    centers={}
    for b in boxes:
        xy=b.get('xyxy')
        if not isinstance(xy,list) or len(xy)!=4 or any(type(v) is not int for v in xy) or not 0<=xy[0]<xy[2]<=width or not 0<=xy[1]<xy[3]<=height:raise ValueError('Invalid measurement box')
        ratios[b['character']]=(xy[3]-xy[1])/height;centers[b['character']]=(xy[0]+xy[2])/2
        if not .25<=ratios[b['character']]<=.35:flags.append('FIGURE_HEIGHT_OUTSIDE_25_35_PERCENT:'+b['character'])
    if centers['A']>=centers['B']:flags.append('CHARACTER_LEFT_RIGHT_ORDER')
    return {'status':'FLAG' if flags else 'PASS_MEASURED_GEOMETRY_ONLY','flags':flags,'height_ratios':ratios,
            'measurement_method':'human_bounding_boxes','reviewer':measurement['reviewer'],
            'identity_style_anatomy':'NOT_EVALUATED','approval_granted':False}
