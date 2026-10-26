"""Loopback-only classroom demo, using real saved outputs and an optional local generation job."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import argparse, json, subprocess, sys, threading, time

HERE = Path(__file__).resolve().parent
RUNS = HERE/'runs'
lock = threading.Lock()
process = None
generation_enabled = False
device = 'auto'
def model_ready():
    try:
        manifest = json.loads((HERE/'model_manifest.json').read_text())
        return manifest['status']=='complete' and len(manifest['models'])==2 and all(Path(m['snapshot']).is_dir() for m in manifest['models']) and (HERE.parent/'repos/BrickGPT/src/brickgpt').is_dir()
    except (OSError, ValueError, KeyError, TypeError):
        return False
def safe_id(value):
    return bool(value) and value.replace('-', '').replace('_', '').isalnum() and len(value)<100

class Handler(BaseHTTPRequestHandler):
    def json(self, value, status=200):
        data=json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store'); self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/config':
            return self.json({'generation_enabled': generation_enabled, 'device': device})
        if path=='/api/runs':
            entries=[]
            for f in sorted(RUNS.glob('*/result.json'),reverse=True):
                try:
                    d=json.loads(f.read_text())
                    entries.append({k:d.get(k) for k in ['run_id','prompt','seed','status','brick_count','generation_seconds','error_type','assets','started']})
                except (ValueError,OSError):continue
            entries.sort(key=lambda x:x.get('started',0),reverse=True)
            return self.json(entries)
        if path.startswith('/api/runs/'):
            rid=path.split('/')[-1]
            if not safe_id(rid):return self.json({'error':'Invalid run'},400)
            folder=RUNS/rid
            try:
                d=json.loads((folder/'result.json').read_text())
                if d['status']!='complete' and (folder/'progress.json').exists():
                    d['progress']=json.loads((folder/'progress.json').read_text())
                # Credentials are never persisted in run records.
                return self.json(d)
            except (OSError,ValueError):return self.json({'error':'Run not ready'},404)
        if path.startswith('/downloads/'):
            pieces=path.split('/')
            allowed={'bricks.txt','bricks.ldr','upstream_bricks.json','result.json','structure.glb','preview.png','assembly_replay.mp4'}
            if len(pieces)!=4 or not safe_id(pieces[2]) or pieces[3] not in allowed:
                return self.json({'error':'Not found'},404)
            target=RUNS/pieces[2]/pieces[3]
            if not target.is_file():return self.json({'error':'Not available'},404)
            data=target.read_bytes();self.send_response(200)
            self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Disposition',f'attachment; filename="{pieces[3]}"')
            self.end_headers();return self.wfile.write(data)
        files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if path not in files:return self.json({'error':'Not found'},404)
        target=HERE/'web'/files[path]
        types={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript'}
        self.send_response(200);self.send_header('Content-Type',types[target.suffix]);self.end_headers()
        self.wfile.write(target.read_bytes())
    def do_POST(self):
        global process
        if self.path!='/api/generate':return self.json({'error':'Not found'},404)
        # No cross-origin browser may trigger local inference jobs.
        origin=self.headers.get('Origin')
        if origin and origin not in [f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}']:
            return self.json({'error':'Origin rejected'},403)
        if not generation_enabled:
            return self.json({'error':'Replay-only mode. Complete installation and model download, then restart without --replay-only to generate.'},503)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=4096:raise ValueError()
            d=json.loads(self.rfile.read(length))
            if not isinstance(d,dict) or not isinstance(d.get('prompt'),str):raise ValueError()
            prompt=d['prompt'].strip();seed=int(d.get('seed',42))
            if not 1<=len(prompt)<=600 or not 0<=seed<=2147483647:raise ValueError()
        except (ValueError,KeyError,TypeError):return self.json({'error':'Provide a prompt and a valid seed'},400)
        with lock:
            if process and process.poll() is None:return self.json({'error':'A generation is already running'},409)
            rid='live-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000)
            (HERE/'logs').mkdir(exist_ok=True)
            with (HERE/'logs'/f'{rid}.log').open('w') as log:
                process=subprocess.Popen([sys.executable,'-u',str(HERE/'run_inference.py'),'--run-id',rid,'--prompt',prompt,'--seed',str(seed),'--device',device],stdout=log,stderr=subprocess.STDOUT)
        self.json({'run_id':rid,'status':'starting'},202)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765)
    p.add_argument('--replay-only',action='store_true')
    p.add_argument('--device',choices=['auto','mps','cuda','cpu'],default='auto');a=p.parse_args()
    generation_enabled = not a.replay_only and model_ready()
    device = a.device
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    print(f'BrickGPT demo: http://127.0.0.1:{a.port}',flush=True)
    server.serve_forever()
