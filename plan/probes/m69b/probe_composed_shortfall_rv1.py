"""m69b-r1: graphed-histogram 0.0.4's shortfall refusal (`_on_compiled` -> `_refuse_shortfall`, which compares ALL
compiled outputs to the marked fill count) under the §5.1 composition (fill nodes first, then another output).
Two fills differing only in weight=[w] vs weight=[w * 1.0] merge in the optimizer: `gh.plan` refuses; the same
fills composed with one counter output are accepted, and the slot's reduce then reads the counter's value.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_composed_shortfall_rv1.py > probe_composed_shortfall_rv1.txt
"""
from __future__ import annotations

import os
import tempfile

import awkward as ak
import boost_histogram as bh
import graphed_histogram as gh
from graphed import aggregate_plan
from graphed.awkward import AwkwardBackend, from_parquet
from graphed import Session
from graphed.core.execution import SequentialRunner
from graphed_histogram.boost import _GroupReduce, _on_compiled, _slots

d = tempfile.mkdtemp(); path = os.path.join(d, "e.parquet")
ak.to_parquet(ak.Array({"x": [1.0, 2.0, 3.0, 4.0], "w": [0.5, 1.0, 1.5, 2.0]}), path)


def build():
    s = Session(AwkwardBackend()); ev = from_parquet(s, "events", path)
    h = gh.boost.Histogram(bh.axis.Regular(4, 0, 5))
    h.fill(ev.x, weight=[ev.w]); h.fill(ev.x, weight=[ev.w * 1.0])
    return ev, h


ev, h = build()
try:
    gh.plan({"h": h})
    print("gh.plan: accepted")
except Exception as e:  # noqa: BLE001
    print(f"gh.plan: {type(e).__name__}: {str(e)[:90]}")

ev, h = build()
fills = h.fill_nodes()
rank = {nid: i for i, nid in enumerate(dict.fromkeys(n.node_id for n in fills))}
n_events = ev.x * 0 + 1
seen = []


class Composed:
    def __init__(self, reduce, n): self.reduce, self.n = reduce, n
    def __call__(self, values):
        seen.append([type(v).__name__ for v in values])
        return self.reduce(values[: self.n])


try:
    p = aggregate_plan(*fills, n_events, reduce=Composed(_GroupReduce(_slots("h", h, rank)), len(rank)),
                       combine=lambda a, b: a, empty=dict, externals=h.evaluators(),
                       on_compiled=_on_compiled((("h", h),), len(rank)))
    print("composed with one more output: accepted")
    try:
        SequentialRunner().run(p)
        print("run: ok; reduce saw", seen[0])
    except Exception as e:  # noqa: BLE001
        print(f"run: {type(e).__name__}: {str(e)[:120]}; reduce saw {seen[0] if seen else None}")
except Exception as e:  # noqa: BLE001
    print(f"composed: {type(e).__name__}: {str(e)[:90]}")
