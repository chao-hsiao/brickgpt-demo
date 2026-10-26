"""Classroom runner around the unmodified upstream BrickGPT generator."""
from pathlib import Path
import argparse, dataclasses, hashlib, json, os, signal, sys, time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
os.environ['HF_HUB_CACHE'] = str(ROOT / 'models/hf-cache')
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
if os.environ.get('HUGGING_FACE_TOKEN'):
    os.environ['HF_TOKEN'] = os.environ['HUGGING_FACE_TOKEN']
sys.path.insert(0, str(ROOT / 'repos/BrickGPT/src'))

def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompt', default='A small stool with a square seat and four short legs.')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--run-id', default=time.strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--device', default='auto', choices=['auto','mps','cpu','cuda'])
    parser.add_argument('--seconds', type=int, default=900)
    args = parser.parse_args()
    if not args.run_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid run id')
    out = HERE / 'runs' / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((HERE / 'model_manifest.json').read_text())
    if manifest['status'] != 'complete':
        raise RuntimeError('Download official weights first')
    from prepare_local_model import prepare
    runtime_adapter = prepare()
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    result = {'run_id': args.run_id, 'prompt': args.prompt, 'seed': args.seed,
              'status': 'loading_model', 'source': 'fresh_official_model_inference',
              'code_commit': 'da01aab83f646a700e2270b66b4c00180523448b',
              'models': manifest['models'], 'started': time.time(),
              'check_mode': 'official_connectivity_fallback',
              'physics_certificate': False,
              'physics_note': 'Restricted Gurobi license rejects even the two-2x6-brick probe. Connectivity is NOT force stability.',
              'config_differences': {'use_gurobi': False, 'max_regenerations': 10},
              'trace_complete': False}
    status_path = out / 'result.json'
    atomic_json(status_path, result)
    def timeout(*_):
        raise TimeoutError('Demo wall-clock budget reached')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.seconds)
    try:
        import torch, transformers
        if args.device == 'auto':
            args.device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        from brickgpt.models import BrickGPT, BrickGPTConfig
        config = BrickGPTConfig(model_name_or_path=str(runtime_adapter), device=args.device,
                                use_gurobi=False, max_regenerations=10)
        result['config'] = dataclasses.asdict(config)
        start = time.perf_counter()
        model = BrickGPT(config)
        result['model_load_seconds'] = time.perf_counter() - start
        result['adapter_attached'] = bool(getattr(model.llm.model, 'peft_config', None))
        if not result['adapter_attached']:
            raise RuntimeError('The official adapter was not attached')
        result['torch_version'] = torch.__version__
        result['transformers_version'] = transformers.__version__
        result['parameter_dtype'] = str(next(model.llm.model.parameters()).dtype)
        result['actual_base_commit'] = getattr(model.llm.model.config, '_commit_hash', None)
        result['status'] = 'generating'
        atomic_json(status_path, result)
        events = []
        original = model.generate_brick_with_rejection_sampling
        def observe(*positional, **kwargs):
            brick, reasons = original(*positional, **kwargs)
            structure = kwargs.get('bricks')
            snapshot = [dataclasses.asdict(b) for b in structure.bricks]
            if brick:
                from brickgpt.data import Brick
                try:
                    snapshot.append(dataclasses.asdict(Brick.from_txt(brick)))
                except ValueError:
                    pass
            event = {'event_index': len(events), 'seconds': time.perf_counter()-generation_start,
                     'current_bricks': len(snapshot), 'brick': brick,
                     'eos': not bool(brick), 'rejections': dict(reasons)}
            events.append(event)
            with (out / 'trace.jsonl').open('a') as f:
                f.write(json.dumps(event)+'\n')
            atomic_json(out / 'progress.json', {'bricks': snapshot, **event})
            if len(events)%10==0 or not brick:
                print(json.dumps(event), flush=True)
            return brick, reasons
        model.generate_brick_with_rejection_sampling = observe
        transformers.set_seed(args.seed)
        generation_start = time.perf_counter()
        with torch.inference_mode():
            output = model(args.prompt)
        if args.device == 'mps':
            torch.mps.synchronize()
        result['generation_seconds'] = time.perf_counter() - generation_start
        bricks = output['bricks']
        result.update({'status': 'complete', 'bricks': [dataclasses.asdict(b) for b in bricks.bricks],
            'brick_count': len(bricks.bricks), 'occupied_cells': int((bricks.voxel_occupancy>0).sum()),
            'valid_geometry': not bricks.has_out_of_bounds_bricks() and not bricks.has_collisions(),
            'connected_to_ground': bool(bricks.is_connected()), 'force_stability': 'not_certified',
            'rejection_reasons': dict(output['rejection_reasons']),
            'regenerations': output['n_regenerations'],
            'model_eos_observed': bool(events and events[-1]['eos']),
            'max_bricks_reached': len(bricks.bricks) >= config.max_bricks,
            'trace_complete': True})
        (out / 'bricks.txt').write_text(bricks.to_txt())
        (out / 'bricks.ldr').write_text(bricks.to_ldr())
        atomic_json(out / 'upstream_bricks.json', bricks.to_json())
        result['output_sha256'] = hashlib.sha256((out/'bricks.txt').read_bytes()).hexdigest()
        # Try the genuine static solver on this fresh output, without claiming a fallback is physics.
        try:
            result['gurobi_score_max'] = float(bricks.stability_scores().max())
            result['force_stability'] = 'passed' if result['gurobi_score_max'] < 1 else 'failed'
        except Exception as exc:
            result['gurobi_error_type'] = type(exc).__name__
            result['gurobi_error_code'] = getattr(exc, 'errno', None)
        atomic_json(status_path, result)
        print(json.dumps({k:v for k,v in result.items() if k not in ['bricks','models','config']}), flush=True)
        try:
            from make_assets import export
            export(out)
        except Exception as asset_error:
            print(json.dumps({'asset_export_error':type(asset_error).__name__}),flush=True)
    except Exception as exc:
        result.update({'status': 'failed', 'error_type': type(exc).__name__, 'error_message': str(exc)[:350]})
        atomic_json(status_path, result)
        print(json.dumps({'status':'failed','type':type(exc).__name__,'message':str(exc)[:350]}), flush=True)
        raise
    finally:
        signal.alarm(0)

if __name__ == '__main__':
    main()
