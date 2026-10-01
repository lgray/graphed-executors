"""r6-B: pickled size of a 10^4-bin local twin per storage the fill-path row backs (bound: > 100 KiB = 102400 B).
Run: PYTHONDONTWRITEBYTECODE=1 ~/vibe-coding/cloud/.venv-m69b/bin/python probe_twin_pickle_rv6b.py"""
import pickle

import boost_histogram as bh

for name, storage in (("Weight", bh.storage.Weight()), ("Double", bh.storage.Double()), ("Int64", bh.storage.Int64())):
    for axes in ((bh.axis.Regular(10000, 0, 1),), (bh.axis.Regular(100, 0, 1), bh.axis.Regular(100, 0, 1))):
        h = bh.Histogram(*axes, storage=storage)
        n = len(pickle.dumps(h))
        print(f"{name:6s} {'x'.join(str(len(a)) for a in axes):9s}: {n:6d} B  > 100 KiB: {n > 102400}")
