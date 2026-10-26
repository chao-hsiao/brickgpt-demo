"""Real force/rollback tests; skipped in lightweight replay-only CI."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
AVAILABLE=(ROOT/'repos/BrickGPT/src/brickgpt').exists() and all(importlib.util.find_spec(n) for n in ['numpy','scipy','gurobipy'])

@unittest.skipUnless(AVAILABLE,'Optional local ML/solver environment and official source required')
class ForceModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path[:0]=[str(ROOT/'demo'),str(ROOT/'repos/BrickGPT/src')]
        from physics_backend import configure
        from brickgpt.data import BrickStructure
        cls.configure=staticmethod(configure)
        cls.Structure=BrickStructure

    def test_highs_ground_pair(self):
        self.configure('highs')
        self.assertTrue(self.Structure.from_txt('2x6 (0,0,0)\n2x6 (2,0,0)').is_stable())

    def test_highs_connected_does_not_mean_force_stable(self):
        self.configure('highs')
        b=self.Structure.from_txt('1x1 (0,0,0)\n'+''.join(f'1x8 (0,0,{z})\n' for z in range(1,16)))
        self.assertTrue(b.is_connected())
        self.assertFalse(b.is_stable())

    def test_official_gurobi_on_large_force_problem(self):
        self.configure('gurobi')
        b=self.Structure.from_txt('1x1 (0,0,0)\n'+''.join(f'1x8 (0,0,{z})\n' for z in range(1,16)))
        try:self.assertFalse(b.is_stable())
        except Exception as e:
            if getattr(e,'errno',None) in [10009,10010]:self.skipTest('Full Gurobi license unavailable on this machine')
            raise

    def test_original_physics_rollback_keeps_stable_prefix(self):
        self.configure('highs')
        from brickgpt.models import BrickGPT
        b=self.Structure.from_txt('1x1 (0,0,0)\n'+''.join(f'1x8 (0,0,{z})\n' for z in range(1,16)))
        # No substitute algorithm or language-model output: call the original
        # prefix-pruning method on an explicitly constructed unstable fixture.
        model=object.__new__(BrickGPT)
        model.use_gurobi=True
        kept=model._remove_all_bricks_after_first_unstable_brick(b)
        self.assertLess(len(kept),len(b))
        self.assertTrue(kept.is_stable())

if __name__=='__main__':unittest.main()
