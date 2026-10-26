"""Portable replay/preview from actual decoded bricks; no generative image model."""
from pathlib import Path
import argparse, json, math, shutil, subprocess, textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PALETTE=['#d5ed82','#c0db6c','#9fbf62','#7fa858','#608e55','#477655']
FONT=next((str(p) for p in [Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()),None)
def font(size):
    return ImageFont.truetype(FONT,size) if FONT else ImageFont.load_default(size=size)
def draw_frame(data,count=None,yaw=-.72,video=False):
    bricks=data['bricks'];n=len(bricks) if count is None else count
    width,height=1000,760
    im=Image.new('RGB',(width,height),'#141b17');d=ImageDraw.Draw(im)
    title=font(28);body=font(18);small=font(14)
    d.text((38,27),'BRICKGPT / '+('ASSEMBLY REPLAY' if video else 'FRESH MODEL OUTPUT'),fill='#d6ef7f',font=title)
    for i,line in enumerate(textwrap.wrap(data['prompt'],88)):
        d.text((38,74+i*24),line,font=body,fill='#edf3e9')
    lo=np.array([min(b['x'] for b in bricks),min(b['y'] for b in bricks),0.])
    hi=np.array([max(b['x']+b['h'] for b in bricks),max(b['y']+b['w'] for b in bricks),max((b['z']+1)*1.2 for b in bricks)])
    center=(lo+hi)/2;extent=max(hi-lo);scale=430/max(extent,5);el=.63
    def project(v):
        x,y,z=np.asarray(v)-center;xx=x*math.cos(yaw)-y*math.sin(yaw);yy=x*math.sin(yaw)+y*math.cos(yaw)
        return (width*.5+xx*scale,height*.53+(yy*math.sin(el)-z*math.cos(el))*scale,yy*math.cos(el)+z*math.sin(el))
    for v in range(-20,21,2):
        for pair in [[[center[0]+v,center[1]-20,0],[center[0]+v,center[1]+20,0]],[[center[0]-20,center[1]+v,0],[center[0]+20,center[1]+v,0]]]:
            a,b=map(project,pair);d.line([a[:2],b[:2]],fill='#28342a',width=1)
    defs=[([4,5,6,7],[0,0,1],1),([1,2,6,5],[1,0,0],.75),([0,4,7,3],[-1,0,0],.63),([2,3,7,6],[0,1,0],.83),([0,1,5,4],[0,-1,0],.67)]
    faces=[]
    for b in bricks[:n]:
        x,y,z=b['x']+.025,b['y']+.025,b['z']*1.2+.025;X,Y,Z=b['x']+b['h']-.025,b['y']+b['w']-.025,(b['z']+1)*1.2-.025
        vertices=list(map(project,[[x,y,z],[X,y,z],[X,Y,z],[x,Y,z],[x,y,Z],[X,y,Z],[X,Y,Z],[x,Y,Z]]))
        color=PALETTE[b['z']%len(PALETTE)]
        for indices,normal,shade in defs:
            facing=(normal[0]*math.sin(yaw)+normal[1]*math.cos(yaw))*math.cos(el)+normal[2]*math.sin(el)
            if facing<=0:continue
            points=[vertices[i] for i in indices];rgb=tuple(int(int(color[j:j+2],16)*shade) for j in [1,3,5])
            faces.append((sum(p[2] for p in points)/4,[p[:2] for p in points],rgb))
    for _,points,color in sorted(faces):d.polygon(points,fill=color,outline='#2f4930')
    d.rectangle((25,646,975,735),fill='#1c251f')
    device=data.get('config',{}).get('device','unknown').upper()
    d.text((40,660),f'{n}/{len(bricks)} bricks | seed {data["seed"]} | generation {data["generation_seconds"]:.1f}s | {device}',font=body,fill='#edf3e9')
    legacy=data.get('check_mode')=='official_connectivity_fallback'
    force_line='Legacy connectivity-only inference; no force certificate.' if legacy else f'Static force model: {data.get("force_stability","unchecked").upper()} | {data.get("solver","unknown")} | rollback {"ON" if data.get("mode")=="full" else "OFF"}'
    if data.get('source')=='first_draft_from_full_inference_trace':
        force_line=f'Static force model: {data["force_stability"].upper()} | {data["solver"]} | initial draft from same full run'
    d.text((40,690),force_line,font=small,fill='#e7b379')
    d.text((40,713),'Simplified brick-box geometry. Saved-output replay, not live inference or a physical simulation.',font=small,fill='#9ca99f')
    return im

def export(folder):
    folder=Path(folder);data=json.loads((folder/'result.json').read_text())
    if data.get('status')!='complete' or not data.get('bricks'):raise ValueError('A completed model output is required')
    preview=draw_frame(data);preview.save(folder/'preview.png')
    import trimesh
    boxes=[]
    for b in data['bricks']:
        mesh=trimesh.creation.box(extents=[b['h']-.05,b['w']-.05,1.15])
        mesh.apply_translation([b['x']+b['h']/2,b['y']+b['w']/2,(b['z']+.5)*1.2])
        rgb=[int(PALETTE[b['z']%6][i:i+2],16) for i in [1,3,5]]+[255]
        mesh.visual.face_colors=rgb;boxes.append(mesh)
    combined=trimesh.util.concatenate(boxes);combined.export(folder/'structure.glb')
    loaded=trimesh.load(folder/'structure.glb',force='mesh')
    assert len(loaded.faces)==len(combined.faces)
    assets={'preview':'preview.png','mesh':'structure.glb'}
    if shutil.which('ffmpeg'):
        frames=180;fps=15
        proc=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1000x760','-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'assembly_replay.mp4')],stdin=subprocess.PIPE)
        try:
            for i in range(frames):
                n=max(1,min(len(data['bricks']),math.ceil((i+1)/100*len(data['bricks']))))
                yaw=-.72+max(0,i-115)*.006
                proc.stdin.write(draw_frame(data,n,yaw,True).tobytes())
            proc.stdin.close();assert proc.wait()==0
        finally:
            if proc.poll() is None:proc.terminate()
        assets['video']='assembly_replay.mp4'
    data['assets']=assets
    (folder/'result.json').write_text(json.dumps(data,indent=2,ensure_ascii=False))
    return assets
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();print(json.dumps(export(a.folder)))
