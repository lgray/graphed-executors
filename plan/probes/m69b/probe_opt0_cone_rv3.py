"""m69b-r3: what does `compile_ir(optimize=False)` ship, the outputs' cone or the whole session arena?

One session reads x and w; an `aggregate_plan` marks `ev.x * 2.0` alone, at opt 1 and opt 0 (the one `compile_ir`
call patched, as probe_opt_level0.py). Recorded but never marked, per case:
  none   nothing else
  cols   50 nodes over `ev.w` (a column the marked output does not read)
  raise  `ev.x[ev.x > 100][0]` (x only; raises on this data if evaluated)
Printed: IR node count and the run's value or error.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt0_cone_rv3.py > probe_opt0_cone_rv3.txt
"""
from __future__ import annotations

import functools
import os
import tempfile

import awkward as ak
import graphed.aggregate as agg
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed.core import GraphStore
from graphed.core.execution import SequentialRunner

REAL = agg.compile_ir
d = tempfile.mkdtemp()
path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": [1.0, 2.0, 3.0], "w": [1.0, 1.0, 1.0]}), path)

for case in ("none", "cols", "raise"):
    for level in (1, 0):
        agg.compile_ir = functools.partial(REAL, optimize=level >= 1)
        try:
            s = Session(AwkwardBackend())
            ev = from_parquet(s, "events", path)
            keep = ev.x * 2.0
            if case == "cols":
                _unrelated = [ev.w + float(i) for i in range(50)]
            if case == "raise":
                _bad = ev.x[ev.x > 100][0]
            plan = aggregate_plan(keep, reduce=lambda v: float(ak.sum(v[0])), combine=lambda a, b: a + b,
                                  empty=float)
            n = len(GraphStore.deserialize(bytes(plan.process.ir)).nodes())
            try:
                res = f"value {SequentialRunner().run(plan).value}"
            except Exception as e:  # noqa: BLE001
                res = f"{type(e).__name__}: {getattr(e, 'cause_type', '')}: {getattr(e, 'cause_message', str(e))[:70]}"
            print(f"{case:5} opt_level={level}: IR nodes {n:2}; {res}")
        finally:
            agg.compile_ir = REAL
