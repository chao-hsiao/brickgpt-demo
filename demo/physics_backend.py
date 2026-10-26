"""Select the original Gurobi solver or the attributed HiGHS force-model backend.

The official force model and inference loop are not edited. HiGHS is a solver
replacement from our teammate, not the solver used in the paper.
"""
import importlib
import numpy as np

SOLVER_SOURCE = 'sauramt/brickgpt-demo@90d6efee0183b2360950340e3c82f83b4f6056e1'
AUDIT_TOL = 1e-8

def configure(solver):
    module=importlib.import_module('brickgpt.stability_analysis.stability_analysis')
    if solver=='gurobi':
        import gurobipy
        module.gp=gurobipy
        module.GRB=gurobipy.GRB
        return {'solver':'gurobi','implementation':'original official solver','version':'.'.join(map(str,gurobipy.gurobi.version()))}
    if solver!='highs':
        raise ValueError('Unknown force solver')
    from vendor import highs_gp
    # Keep the teammate backend unmodified. Audit each solution against the
    # original forms of the constraints before it can produce a stable verdict.
    class AuditedModel(highs_gp.Model):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.original_constraints=[]
        def addConstr(self,c,name=''):
            self.original_constraints.append(c)
            return super().addConstr(c,name)
        def optimize(self):
            super().optimize()
            if self.Status!=highs_gp.GRB.Status.OPTIMAL:
                raise RuntimeError('HiGHS did not return an optimal force solution')
            x=self._x
            def value(e):
                e=highs_gp.LinExpr.of(e)
                return e.const+sum(c*x[i] for i,c in e.terms.items())
            violations=[]
            for c in self.original_constraints:
                if isinstance(c,highs_gp._LinConstr):v=abs(value(c.expr))
                elif isinstance(c,highs_gp._AbsConstr):v=abs(x[c.t.idx]-abs(value(c.x)))
                elif isinstance(c,highs_gp._MaxConstr):v=abs(x[c.m.idx]-max(value(y) for y in c.xs))
                elif isinstance(c,highs_gp._ComplementarityConstr):v=abs(x[c.a.idx]*x[c.b.idx])
                else:raise RuntimeError('Unrecognised original force constraint')
                violations.append(v)
            bound=max((max(lo-x[i],0,x[i]-hi) for i,(lo,hi) in enumerate(zip(self._lb,self._ub))),default=0)
            maximum=max([bound,*violations],default=0)
            self.solve_info['original_constraint_max_violation']=float(maximum)
            if not np.isfinite(maximum) or maximum>AUDIT_TOL:
                raise RuntimeError(f'Force solution failed original-constraint audit: {maximum:g}')
    # Avoid changing the imported backend's class globally.
    from types import SimpleNamespace
    proxy=SimpleNamespace(**{k:getattr(highs_gp,k) for k in ['GRB','quicksum','abs_','max_']},Model=AuditedModel)
    module.gp=proxy
    module.GRB=highs_gp.GRB
    return {'solver':'highs','implementation':SOLVER_SOURCE,
            'zero_snap_tolerance':highs_gp.ZERO_TOL,'original_constraint_audit_tolerance':AUDIT_TOL}
