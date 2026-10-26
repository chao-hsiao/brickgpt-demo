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
    parser.add_argument('--mode', choices=['full','no_rollback','connectivity'], default='full')
    parser.add_argument('--solver', choices=['highs','gurobi'], default='gurobi')
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
              'check_mode': 'official_connectivity_fallback' if args.mode=='connectivity' else 'force_model',
              'mode': args.mode, 'solver': args.solver,
              'physics_certificate': False,
              'physics_note': 'Static force model only; not impact/fracture simulation or a real-world guarantee.',
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
        from physics_backend import configure
        result['solver_backend'] = configure(args.solver)
        # Detect a missing/size-limited license before loading or running the LLM.
        from brickgpt.data import BrickStructure
        probe=BrickStructure.from_txt('2x6 (0,0,0)\n2x6 (2,0,0)\n')
        if not probe.is_stable():
            raise RuntimeError('Static solver preflight did not validate the ground-brick pair')
        regenerations=0 if args.mode=='no_rollback' else 100
        config = BrickGPTConfig(model_name_or_path=str(runtime_adapter), device=args.device,
                                use_gurobi=args.mode!='connectivity', max_regenerations=regenerations)
        result['config_differences']={'solver':args.solver,'use_gurobi':config.use_gurobi,'max_regenerations':regenerations}
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
        physics_checks=[]
        rollbacks=[]
        original_check=model._is_stable
        def checked(structure):
            before=time.perf_counter()
            stable=bool(original_check(structure))
            check={'bricks':len(structure),'stable':stable,'seconds':time.perf_counter()-before,
                   'kind':'force' if config.use_gurobi else 'connectivity','stage':'inference'}
            physics_checks.append(check)
            atomic_json(out/'physics_checks.json',physics_checks)
            print(json.dumps({'physics_check':check}),flush=True)
            return stable
        model._is_stable=checked
        original_rollback=model._remove_all_bricks_after_first_unstable_brick
        def rolled(structure):
            kept=original_rollback(structure)
            event={'before':len(structure),'kept':len(kept),'seconds':time.perf_counter()-generation_start}
            rollbacks.append(event)
            atomic_json(out/'rollbacks.json',rollbacks)
            print(json.dumps({'rollback':event}),flush=True)
            return kept
        model._remove_all_bricks_after_first_unstable_brick=rolled
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
            'physics_checks': physics_checks, 'rollbacks': rollbacks,
            'model_eos_observed': bool(events and events[-1]['eos']),
            'max_bricks_reached': len(bricks.bricks) >= config.max_bricks,
            'trace_complete': True})
        (out / 'bricks.txt').write_text(bricks.to_txt())
        (out / 'bricks.ldr').write_text(bricks.to_ldr())
        atomic_json(out / 'upstream_bricks.json', bricks.to_json())
        result['output_sha256'] = hashlib.sha256((out/'bricks.txt').read_bytes()).hexdigest()
        # Full final analysis is performed even for the rollback-off ablation.
        try:
            force_start=time.perf_counter()
            scores=bricks.stability_scores()
            result['force_score_max'] = float(scores.max())
            result['brick_stress']=[float(scores[b.slice].max()) for b in bricks.bricks]
            stable=result['valid_geometry'] and not bricks.has_floating_bricks() and len(bricks)>0 and result['force_score_max']<1
            result['force_stability'] = 'passed' if stable else 'failed'
            physics_checks.append({'bricks':len(bricks),'stable':bool(stable),'seconds':time.perf_counter()-force_start,'kind':'force','stage':'final'})
        except Exception as exc:
            result['force_error_type'] = type(exc).__name__
            result['force_error_code'] = getattr(exc, 'errno', None)
            result['force_error_message'] = str(exc)[:240]
            if args.mode!='connectivity':
                raise
        atomic_json(out/'physics_checks.json',physics_checks)
        atomic_json(out/'rollbacks.json',rollbacks)
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
