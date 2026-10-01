#!/bin/bash
# submituser in the pool container: how long `python -c pass` (the m68a test's child) takes to exit, bare and
# with test-htcondor's coverage .pth active (COVERAGE_PROCESS_START), against the test's 1.0 s window.
cd /work; export PATH=/opt/venv/bin:$PATH
for mode in bare coverage; do
  if [ $mode = coverage ]; then export COVERAGE_PROCESS_START=/work/.coveragerc-htcondor COVERAGE_FILE=/tmp/rv-child.cov; fi
  python - <<'PY'
import os, subprocess, sys, time
ts = []
for _ in range(20):
    t = time.monotonic(); subprocess.run([sys.executable, "-c", "pass"], check=True); ts.append(time.monotonic() - t)
ts.sort()
print(f"{'coverage' if os.environ.get('COVERAGE_PROCESS_START') else 'bare':8} n=20 median={ts[10]:.3f}s max={ts[-1]:.3f}s")
PY
done
rm -f /tmp/rv-child.cov*
