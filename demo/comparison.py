"""Save a genuine initial draft and link it to its own completed inference run."""
from pathlib import Path
from collections import Counter
import argparse
import dataclasses
import hashlib
import json
import sys
import time


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)


def initial_snapshot(events, expected_count):
    """Only the first generation attempt; never combine later regenerated bricks."""
    captured, lines, reasons = [], [], Counter()
    for event in events:
        # A max-brick termination has no EOS. The rollback record provides the
        # exact boundary, so the next attempt must not leak into this snapshot.
        if len(lines) == expected_count and not event.get('eos'):
            break
        captured.append(event)
        if event.get('eos'):
            break
        if not event.get('brick'):
            raise ValueError('Initial draft contains an incomplete brick event')
        lines.append(event['brick'].strip())
        reasons.update(event.get('rejections', {}))
    if not lines or len(lines) != expected_count:
        raise ValueError('Trace does not match the first rollback structure')
    return {
        'text': '\n'.join(lines) + '\n', 'events': captured,
        'seconds': captured[-1]['seconds'],
        'eos': bool(captured[-1].get('eos')),
        'rejection_reasons': dict(reasons),
    }


def analyze_draft(text, parent):
    # No language model is loaded or sampled. This only reads the saved layout
    # and applies the same force backend used by its parent generation run.
    from brickgpt.data import BrickStructure
    from physics_backend import configure
    configure(parent['solver'])
    structure = BrickStructure.from_txt(text)
    valid = not structure.has_out_of_bounds_bricks() and not structure.has_collisions()
    data = {
        'bricks': [dataclasses.asdict(b) for b in structure.bricks],
        'brick_count': len(structure),
        'occupied_cells': int((structure.voxel_occupancy > 0).sum()),
        'valid_geometry': valid,
        'connected_to_ground': bool(structure.is_connected()),
        'force_stability': 'not_certified',
    }
    start = time.perf_counter()
    try:
        scores = structure.stability_scores()
        maximum = float(scores.max())
        stable = bool(valid and not structure.has_floating_bricks() and maximum < 1)
        data.update(force_score_max=maximum,
                    brick_stress=[float(scores[b.slice].max()) for b in structure.bricks],
                    force_stability='passed' if stable else 'failed',
                    physics_checks=[{'bricks': len(structure), 'stable': stable,
                                     'seconds': time.perf_counter() - start,
                                     'kind': 'force', 'stage': 'draft_reanalysis'}])
    except Exception as error:
        # Keep a useful comparison without inventing a force verdict or colors
        # when a replay machine cannot run the optional solver.
        data.update(force_error_type=type(error).__name__, physics_checks=[])
    return data, {'bricks.ldr': structure.to_ldr(),
                  'upstream_bricks.json': json.dumps(structure.to_json(), indent=2)}


def ensure_comparison(folder, analyze=None):
    folder = Path(folder)
    parent_path = folder / 'result.json'
    parent = json.loads(parent_path.read_text())
    if (parent.get('status') != 'complete' or parent.get('mode') != 'full'
            or parent.get('check_mode') != 'force_model'
            or not parent.get('trace_complete') or not parent.get('rollbacks')):
        return None
    run_id = parent['run_id']
    if run_id != folder.name or not run_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid source run identity')
    existing_id = parent.get('comparison_run_id')
    if existing_id:
        if not existing_id.replace('-', '').replace('_', '').isalnum() or len(existing_id) >= 100:
            raise ValueError('Invalid saved comparison identity')
        existing = json.loads((folder.parent / existing_id / 'result.json').read_text())
        if (existing.get('comparison_run_id') != run_id
                or existing.get('mode') != 'first_draft'
                or existing.get('status') != 'complete'):
            raise ValueError('Saved comparison does not point back to its source')
        return existing_id
    draft_id = run_id + '-first-draft'
    if len(draft_id) >= 100:
        draft_id = run_id[:75] + '-draft-' + hashlib.sha256(run_id.encode()).hexdigest()[:8]
    destination = folder.parent / draft_id
    if destination.exists():
        # Do not overwrite an unrelated user run or an incomplete prior export.
        raise FileExistsError('Initial-draft destination already exists')
    events = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    snapshot = initial_snapshot(events, parent['rollbacks'][0]['before'])
    data, files = (analyze or analyze_draft)(snapshot['text'], parent)
    if data['brick_count'] != parent['rollbacks'][0]['before']:
        raise ValueError('Parsed draft does not match the recorded rollback')
    metadata = ['prompt', 'seed', 'models', 'code_commit', 'check_mode', 'solver',
                'solver_backend', 'config', 'config_differences', 'adapter_attached',
                'parameter_dtype', 'torch_version', 'transformers_version', 'actual_base_commit',
                'physics_note', 'model_load_seconds']
    draft = {key: parent[key] for key in metadata if key in parent}
    draft.update(data, run_id=draft_id, status='complete', mode='first_draft',
                 source='first_draft_from_full_inference_trace', source_run_id=run_id,
                 comparison_run_id=run_id, started=parent.get('started', 0) - .001,
                 generation_seconds=snapshot['seconds'], regenerations=0, rollbacks=[],
                 rejection_reasons=snapshot['rejection_reasons'],
                 model_eos_observed=snapshot['eos'], trace_complete=True,
                 physics_certificate=False,
                 output_sha256=hashlib.sha256(snapshot['text'].encode()).hexdigest())
    destination.mkdir()
    (destination / 'bricks.txt').write_text(snapshot['text'])
    for name, content in files.items():
        (destination / name).write_text(content)
    (destination / 'trace.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in snapshot['events']))
    atomic_json(destination / 'physics_checks.json', draft.get('physics_checks', []))
    atomic_json(destination / 'rollbacks.json', [])
    atomic_json(destination / 'result.json', draft)
    # Publish the link only after the genuine draft is ready for the API.
    parent['comparison_run_id'] = draft_id
    parent.pop('comparison_error_type', None)
    atomic_json(parent_path, parent)
    return draft_id


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'repos/BrickGPT/src'))
    print(json.dumps({'comparison_run_id': ensure_comparison(args.folder)}))
