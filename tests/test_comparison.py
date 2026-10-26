"""Trace-based comparison must never fabricate or mix independent generations."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('comparison', ROOT / 'demo/comparison.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'new-user-run'
        self.folder.mkdir()
        self.parent = {'run_id': self.folder.name, 'prompt': 'A table.', 'seed': 42,
                       'status': 'complete', 'mode': 'full', 'check_mode': 'force_model',
                       'trace_complete': True, 'solver': 'gurobi', 'started': 10,
                       'brick_count': 2, 'force_stability': 'passed',
                       'rollbacks': [{'before': 3, 'kept': 1}]}
        self.events = [
            {'brick': '2x2 (0,0,0)\n', 'seconds': 1, 'eos': False, 'rejections': {'collision': 2}},
            {'brick': '2x2 (0,0,1)\n', 'seconds': 2, 'eos': False},
            {'brick': '2x2 (2,0,1)\n', 'seconds': 3, 'eos': False},
            {'brick': '', 'seconds': 4, 'eos': True},
            {'brick': '2x2 (0,0,2)\n', 'seconds': 5, 'eos': False},
            {'brick': '', 'seconds': 6, 'eos': True},
        ]
        self.write_parent()
        self.write_trace()

    def write_parent(self):
        (self.folder / 'result.json').write_text(json.dumps(self.parent))

    def write_trace(self):
        (self.folder / 'trace.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in self.events))

    @staticmethod
    def describe_fixture(text, parent):
        # An explicit fixture verdict, not a mock model generation or a claim
        # that these tests certify physical stability. Real solver checks are
        # separate optional tests and saved-run backfill verification.
        return {'brick_count': len(text.splitlines()), 'force_stability': 'failed'}, {'bricks.ldr': 'fixture'}

    def test_new_user_run_gets_its_own_genuine_draft(self):
        final_before = dict(self.parent)
        draft_id = comparison.ensure_comparison(self.folder, self.describe_fixture)
        draft_folder = self.folder.parent / draft_id
        draft = json.loads((draft_folder / 'result.json').read_text())
        self.assertEqual((draft_folder / 'bricks.txt').read_text().splitlines(),
                         [e['brick'].strip() for e in self.events[:3]])
        self.assertNotIn('(0,0,2)', (draft_folder / 'bricks.txt').read_text())
        self.assertEqual(draft['source_run_id'], self.folder.name)
        self.assertEqual(draft['comparison_run_id'], self.folder.name)
        self.assertEqual(draft['generation_seconds'], 4)
        self.assertEqual(draft['rejection_reasons'], {'collision': 2})
        self.assertEqual(draft['mode'], 'first_draft')
        self.assertEqual(draft['force_stability'], 'failed')
        final = json.loads((self.folder / 'result.json').read_text())
        self.assertEqual(final.pop('comparison_run_id'), draft_id)
        self.assertEqual(final, final_before)
        self.assertEqual(comparison.ensure_comparison(self.folder), draft_id)

    def test_rollback_off_and_no_rollback_have_no_false_pair(self):
        for change in [{'mode': 'no_rollback'}, {'rollbacks': []},
                       {'status': 'generating'}, {'trace_complete': False},
                       {'check_mode': 'official_connectivity_fallback'}]:
            self.parent.update(change)
            self.write_parent()
            self.assertIsNone(comparison.ensure_comparison(self.folder, self.describe_fixture))
            self.parent.update(mode='full', rollbacks=[{'before': 3, 'kept': 1}],
                               status='complete', trace_complete=True, check_mode='force_model')
        self.assertEqual(len(list(self.folder.parent.iterdir())), 1)

    def test_incomplete_or_mismatched_trace_does_not_relabel_final(self):
        self.events = self.events[:2]
        self.write_trace()
        with self.assertRaises(ValueError):
            comparison.ensure_comparison(self.folder, self.describe_fixture)
        self.assertEqual(json.loads((self.folder / 'result.json').read_text()), self.parent)

    def test_existing_user_folder_is_preserved(self):
        other = self.folder.parent / (self.folder.name + '-first-draft')
        other.mkdir()
        (other / 'user.txt').write_text('Keep this user data')
        with self.assertRaises(FileExistsError):
            comparison.ensure_comparison(self.folder, self.describe_fixture)
        self.assertEqual((other / 'user.txt').read_text(), 'Keep this user data')
        self.assertNotIn('comparison_run_id', json.loads((self.folder / 'result.json').read_text()))

    def test_max_brick_termination_does_not_capture_the_next_attempt(self):
        events = self.events[:3] + self.events[4:]
        snapshot = comparison.initial_snapshot(events, 3)
        self.assertEqual(len(snapshot['text'].splitlines()), 3)
        self.assertFalse(snapshot['eos'])
        self.assertEqual(snapshot['seconds'], 3)

    def test_unrelated_existing_link_is_refused(self):
        self.parent['comparison_run_id'] = '../outside'
        self.write_parent()
        with self.assertRaises(ValueError):
            comparison.ensure_comparison(self.folder, self.describe_fixture)


if __name__ == '__main__':
    unittest.main()
