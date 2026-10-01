"""r5-B: does a Receipt(spec, endpoint, hist_id) pickle at one length for 10- and 10^4-bin twins?
Run: graphed-histogram/.venv/bin/python probe_receipt_length_rv5b.py > probe_receipt_length_rv5b.txt"""
import pickle
import uuid
from dataclasses import dataclass

import boost_histogram as bh
from graphed_histogram._spec import spec_of


@dataclass(frozen=True)
class Receipt:  # the plan's fields, module-level as the implementation's would be
    spec: str
    endpoint: str
    hist_id: str


hid = uuid.uuid4().hex
for label, axes in [
    ("Regular(10,0,1) vs Regular(10000,0,1)", (bh.axis.Regular(10, 0, 1), bh.axis.Regular(10000, 0, 1))),
    ("Regular(100,0,1)x2 (10^4 bins) vs Regular(10,0,1)", (bh.axis.Regular(10, 0, 1), None)),
]:
    small = bh.Histogram(axes[0], storage=bh.storage.Weight())
    big = bh.Histogram(axes[1], storage=bh.storage.Weight()) if axes[1] is not None else bh.Histogram(
        bh.axis.Regular(100, 0, 1), bh.axis.Regular(100, 0, 1), storage=bh.storage.Weight())
    rs = Receipt(spec_of(small), "tcp://127.0.0.1:10000", hid)
    rb = Receipt(spec_of(big), "tcp://127.0.0.1:10000", hid)
    print(f"{label}: receipt pickles {len(pickle.dumps({'h': rs}))} vs {len(pickle.dumps({'h': rb}))} B;"
          f" histograms pickle {len(pickle.dumps(small))} vs {len(pickle.dumps(big))} B")
