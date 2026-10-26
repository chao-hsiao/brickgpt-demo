"""Exercise the real loopback API without downloading or mocking a model."""
from pathlib import Path
import hashlib
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
import tempfile
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('demo_server', ROOT/'demo/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class ReplayAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.generation_enabled = False
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = 'http://127.0.0.1:'+str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        with urllib.request.urlopen(self.url+path, timeout=5) as response:
            return response.read()

    def post_error(self, payload, status, origin=None):
        headers={'Content-Type':'application/json'}
        if origin: headers['Origin']=origin
        request=urllib.request.Request(self.url+'/api/generate',data=json.dumps(payload).encode(),headers=headers)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code,status)
        raised.exception.close()

    def test_page_has_model_card_and_clean_brand(self):
        page=self.get('/').decode()
        self.assertIn('<span>▦</span> BRICKGPT</a>',page)
        self.assertIn('meta-llama/Llama-3.2-1B-Instruct',page)
        self.assertIn('AvaLovelace/BrickGPT',page)

    def test_config_reflects_replay_mode(self):
        self.assertFalse(json.loads(self.get('/api/config'))['generation_enabled'])

    def test_reference_hashes_and_provenance(self):
        for rid in ['live-20261026-214335','stool_seed42_scipyfix']:
            result=json.loads(self.get('/api/runs/'+rid))
            self.assertEqual(result['brick_count'],len(result['bricks']))
            self.assertTrue(result['adapter_attached'])
            self.assertTrue(result['model_eos_observed'])
            self.assertEqual(result['force_stability'],'not_certified')
            actual=hashlib.sha256(self.get('/downloads/'+rid+'/bricks.txt')).hexdigest()
            self.assertEqual(actual,result['output_sha256'])

    def test_replay_assets_download(self):
        rid='live-20261026-214335'
        self.assertTrue(self.get('/downloads/'+rid+'/structure.glb').startswith(b'glTF'))
        self.assertIn(b'ftyp',self.get('/downloads/'+rid+'/assembly_replay.mp4')[:32])

    def test_file_allowlist(self):
        for path in ['/downloads/live-20261026-214335/trace.jsonl','/.env','/downloads/../server.py']:
            with self.assertRaises(urllib.error.HTTPError) as raised:self.get(path)
            self.assertEqual(raised.exception.code,404)
            raised.exception.close()

    def test_replay_refuses_generation(self):
        self.post_error({'prompt':'A chair.','seed':42},503)
        self.assertIsNone(server.process)

    def test_force_comparison_preserves_initial_trace(self):
        full=json.loads(self.get('/api/runs/gurobi-table-s42-full'))
        draft=json.loads(self.get('/api/runs/gurobi-table-s42-first-draft'))
        self.assertEqual(full['force_stability'],'passed')
        self.assertEqual(draft['force_stability'],'failed')
        self.assertEqual(draft['source'],'first_draft_from_full_inference_trace')
        self.assertEqual(draft['mode'],'first_draft')
        self.assertEqual(full['rollbacks'],[{'before':174,'kept':3,'seconds':full['rollbacks'][0]['seconds']}])
        events=[json.loads(line) for line in (ROOT/'demo/runs/gurobi-table-s42-full/trace.jsonl').read_text().splitlines()]
        initial=[]
        for e in events:
            if e['eos']:break
            initial.append(e['brick'].rstrip('\n'))
        saved=self.get('/downloads/gurobi-table-s42-first-draft/bricks.txt').decode().splitlines()
        self.assertEqual(initial,saved)

    def test_api_passes_selected_solver_and_rollback_mode(self):
        server.generation_enabled=True
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(server,'HERE',Path(tmp)), patch.object(server.subprocess,'Popen',return_value=Mock()) as spawn:
                req=urllib.request.Request(self.url+'/api/generate',data=json.dumps({'prompt':'A table.','seed':42,'mode':'no_rollback','solver':'gurobi'}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as response:self.assertEqual(response.status,202)
                args=spawn.call_args.args[0]
                self.assertEqual(args[args.index('--mode')+1],'no_rollback')
                self.assertEqual(args[args.index('--solver')+1],'gurobi')
        finally:
            server.process=None
            server.generation_enabled=False

    def test_foreign_origin_refused(self):
        self.post_error({'prompt':'A chair.'},403,origin='https://example.com')

    def test_invalid_payloads_refused_without_starting_model(self):
        server.generation_enabled=True
        try:
            for payload in [[],{}, {'prompt':4}, {'prompt':' '}, {'prompt':'A chair.','seed':-1}]:
                self.post_error(payload,400)
            self.assertIsNone(server.process)
        finally:
            server.generation_enabled=False

if __name__=='__main__':unittest.main()
