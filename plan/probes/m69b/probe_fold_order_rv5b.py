"""r5-B: is a SubmitRunner-style tree fold of per-partition Weight histograms bit-equal to the server's arrival
(left) fold, with the m69b MC fixture's weights (lognormal magnitudes x random signs, float32)?
Run: graphed-histogram/.venv/bin/python probe_fold_order_rv5b.py > probe_fold_order_rv5b.txt"""
import boost_histogram as bh
import numpy as np

rng = np.random.default_rng(3)
for n in (2, 3, 4):
    parts = []
    for _ in range(n):
        x = rng.uniform(100, 180, 4000)
        w = (rng.lognormal(0, 1, 4000) * rng.choice([-1, 1], 4000)).astype(np.float32)
        h = bh.Histogram(bh.axis.Regular(80, 100, 180), storage=bh.storage.Weight())
        parts.append(h.fill(x, weight=w))
    left = parts[0]
    for p in parts[1:]:
        left = left + p
    tree = parts[0] + parts[1] if n == 2 else (parts[0] + parts[1]) + (parts[2] + parts[3]) if n == 4 else (parts[0] + parts[1]) + parts[2]
    v, t = left.view(flow=True), tree.view(flow=True)
    differ = int(np.sum((v["value"] != t["value"]) | (v["variance"] != t["variance"])))
    print(f"{n} partials: tree vs left fold differ in {differ} bins")
