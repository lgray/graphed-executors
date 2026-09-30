"""m69b-r3: §5.0's frozen row claims the opt-0 plan PICKLES byte-identically across PYTHONHASHSEED (probe_opt_level0
hashes the IR only). A plan over one fixed parquet path with module-level reduce/combine/empty, at opt 1 and opt 0
(the one `compile_ir` call patched), pickled with the stdlib and hashed.

Run: for s in 1 2; do PYTHONHASHSEED=$s ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python -B probe_opt0_pickle_rv3.py; done > probe_opt0_pickle_rv3.txt
"""
from __future__ import annotations

import functools
import hashlib
import os
import pickle
import sys
import tempfile

import awkward as ak
import graphed.aggregate as agg
from graphed import Session, aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_opt0_pickle_fns_rv3 import combine, empty, reduce  # noqa: E402  (importable by reference)

REAL = agg.compile_ir
d = os.path.join(tempfile.gettempdir(), "m69b_opt0_pickle_rv3")
os.makedirs(d, exist_ok=True)
path = os.path.join(d, "e.parquet")
if not os.path.exists(path):
    ak.to_parquet(ak.Array({"x": [1.0, 2.0, 3.0], "w": [0.5, 1.0, 1.5]}), path)

for level in (1, 0):
    agg.compile_ir = functools.partial(REAL, optimize=level >= 1)
    try:
        s = Session(AwkwardBackend())
        ev = from_parquet(s, "events", path)
        plan = aggregate_plan(ev.x * ev.w, ev.x * 1.0, ev.x, reduce=reduce, combine=combine, empty=empty)
        print(f"seed {os.environ.get('PYTHONHASHSEED')} opt_level={level}: pickled plan sha256 "
              f"{hashlib.sha256(pickle.dumps(plan)).hexdigest()[:16]}, "
              f"ir {hashlib.sha256(bytes(plan.process.ir)).hexdigest()[:16]}")
    finally:
        agg.compile_ir = REAL
