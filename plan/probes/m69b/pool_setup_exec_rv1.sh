#!/bin/bash
# root inside m68b-minicondor:local (/src = the reviewed tree, read-only): the test-htcondor pool config, graphed 7e048bf,
# histogram 3830aca[histserv], and the tree copied to /work and installed editable (the CI install, as submituser runs it).
set -eu
echo "MOUNT_UNDER_SCRATCH =" > /etc/condor/config.d/99-jobs-share-tmp
printf '%s\n' 'use feature : GPUs' 'GPU_DISCOVERY_EXTRA = $(GPU_DISCOVERY_EXTRA) -simulate:2,1' > /etc/condor/config.d/99-sim-gpu
/start.sh > /tmp/start.log 2>&1 &
for i in $(seq 120); do condor_status -schedd -af Name 2>/dev/null | grep -q . && condor_status -af Name 2>/dev/null | grep -q . && break; sleep 2; done
condor_status -af Name State Cpus Memory TotalGPUs
export PATH=/root/.cargo/bin:$PATH
uv pip install --python /opt/venv/bin/python \
  "graphed @ git+https://github.com/graphed-org/graphed@7e048bfdf929f7182885e62c1611e1c2a3357f77" \
  "graphed-histogram[histserv] @ git+https://github.com/graphed-org/graphed-histogram@3830acaa26a9a5860892f263c0b0ca8c96efadb8" \
  grpcio-health-checking 2>&1 | tail -5
rm -rf /work && cp -r /src /work && rm -f /work/.git && chown -R submituser:submituser /work
uv pip install --python /opt/venv/bin/python --no-deps -e /work 2>&1 | tail -2
/opt/venv/bin/python -c "import sysconfig, pathlib; pathlib.Path(sysconfig.get_path('purelib'), 'graphed_subcov.pth').write_text('import coverage; coverage.process_startup()\n')"
/opt/venv/bin/python -c "import graphed_executors, graphed, graphed_histogram, histserv, importlib.metadata as m; print(graphed_executors.__file__, m.distribution('graphed').read_text('direct_url.json'), m.distribution('graphed-histogram').read_text('direct_url.json'), m.version('histserv'))"
echo SETUP-DONE
