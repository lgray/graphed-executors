#!/bin/bash
# root inside m68b-minicondor:local: the test-htcondor pool config and CI pins, then for each tree under /src/<leg>
# (read-only), the frozen htcondor suites as submituser into /out/<leg>.txt (no coverage: pins only).
set -u
echo "MOUNT_UNDER_SCRATCH =" > /etc/condor/config.d/99-jobs-share-tmp
printf '%s\n' 'use feature : GPUs' 'GPU_DISCOVERY_EXTRA = $(GPU_DISCOVERY_EXTRA) -simulate:2,1' > /etc/condor/config.d/99-sim-gpu
/start.sh > /tmp/start.log 2>&1 &
for i in $(seq 120); do condor_status -schedd -af Name 2>/dev/null | grep -q . && condor_status -af Name 2>/dev/null | grep -q . && break; sleep 2; done
condor_status -af Name State Cpus Memory TotalGPUs
export PATH=/root/.cargo/bin:$PATH
uv pip install --python /opt/venv/bin/python \
  "graphed[awkward,numpy] @ git+https://github.com/graphed-org/graphed@7e048bfdf929f7182885e62c1611e1c2a3357f77" \
  "graphed-histogram[histserv] @ git+https://github.com/graphed-org/graphed-histogram@3830acaa26a9a5860892f263c0b0ca8c96efadb8" \
  grpcio-health-checking 2>&1 | tail -3
mkdir -p /out && chown submituser:submituser /out
for leg in "$@"; do
  rm -rf /work && cp -r /src/$leg /work && rm -f /work/.git && chown -R submituser:submituser /work
  uv pip install --python /opt/venv/bin/python --no-deps -e /work 2>&1 | tail -1
  su submituser -s /bin/bash -c "cd /work && export PATH=/opt/venv/bin:\$PATH && \
    python -m pytest -p no:cacheprovider -rfEs -o faulthandler_timeout=300 \
      tests/frozen/m66 tests/frozen/m67 tests/frozen/m68a tests/frozen/m68b tests/frozen/m68c \
      tests/frozen/m69b/test_histserv_cluster.py tests/frozen/m69b/test_histserv_managed.py \
      > /out/$leg.txt 2>&1; echo pytest-exit=\$? >> /out/$leg.txt"
  echo "queue after: $(condor_q -allusers -totals 2>/dev/null | grep 'Total for all users')" >> /out/$leg.txt
  condor_rm -all >/dev/null 2>&1
done
echo POOL-DONE
