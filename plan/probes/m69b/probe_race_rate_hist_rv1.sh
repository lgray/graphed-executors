#!/bin/sh
# Kill rate of the lockless-_Handles mutant against the extra concurrency test, and the real code's pass rate.
# usage: probe_race_rate_hist_rv1.sh <worktree> <python> <runs>
WT=$1; PY=$2; N=${3:-20}; T=tests/extra/m69b/test_histserv_served.py::test_concurrent_first_calls_create_each_histogram_once
cd "$WT" || exit 1
run() { k=0; i=0; while [ $i -lt $N ]; do PYTHONPATH=$WT/src $PY -m pytest -q -p no:cacheprovider -o addopts= "$T" >/dev/null 2>&1 || k=$((k+1)); i=$((i+1)); done; echo "$1: $k/$N runs failed"; }
run real
F=src/graphed_histogram/histserv.py; cp $F /tmp/.hs_rv1_orig.$$
trap 'cp /tmp/.hs_rv1_orig.$$ $F; rm -f /tmp/.hs_rv1_orig.$$' EXIT
$PY - "$F" <<'PY'
import sys; p=sys.argv[1]; t=open(p).read()
old="        with self._lock:\n            if self._ids is None:"; assert t.count(old)==1
open(p,"w").write(t.replace(old,"        if True:\n            if self._ids is None:"))
PY
run lockless-mutant
