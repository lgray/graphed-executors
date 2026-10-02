#!/bin/bash
# m69b ordering TEST_SANITY, root inside m68b-minicondor:local (container m69b-sanity-pool): the test-htcondor
# pool config and the CI pins of 6225cd5 (graphed a51bee4, graphed-histogram 3830acaa), then each line of
# /p/<legs file> "label|tree|pytest args" runs as submituser against /src/<tree> (read-only) into /out/<label>.txt.
set -u
legs=$1
if ! condor_status -schedd -af Name 2>/dev/null | grep -q .; then
  echo "MOUNT_UNDER_SCRATCH =" > /etc/condor/config.d/99-jobs-share-tmp
  printf '%s\n' 'use feature : GPUs' 'GPU_DISCOVERY_EXTRA = $(GPU_DISCOVERY_EXTRA) -simulate:2,1' > /etc/condor/config.d/99-sim-gpu
  setsid /start.sh > /tmp/start.log 2>&1 < /dev/null &
  for i in $(seq 120); do condor_status -schedd -af Name 2>/dev/null | grep -q . && condor_status -af Name 2>/dev/null | grep -q . && break; sleep 2; done
fi
condor_status -af Name State Cpus Memory TotalGPUs
export PATH=/root/.cargo/bin:$PATH
if [ ! -f /tmp/pins-done ]; then
  uv pip install --python /opt/venv/bin/python \
    "graphed[awkward,numpy] @ git+https://github.com/graphed-org/graphed@a51bee4ff0b40c33cd68cca593f8a74c11d9f516" \
    "graphed-histogram[histserv] @ git+https://github.com/graphed-org/graphed-histogram@3830acaa26a9a5860892f263c0b0ca8c96efadb8" \
    grpcio-health-checking 2>&1 | tail -3 && touch /tmp/pins-done
fi
mkdir -p /out && chown submituser:submituser /out
while IFS='|' read -r label tree args; do
  [ -z "$label" ] && continue
  rm -rf /work && cp -r /src/$tree /work && chown -R submituser:submituser /work
  uv pip install --python /opt/venv/bin/python --no-deps -e /work 2>&1 | tail -1
  su submituser -s /bin/bash -c "cd /work && export PATH=/opt/venv/bin:\$PATH && \
    python -m pytest -p no:cacheprovider -rA -o faulthandler_timeout=600 $args \
      > /out/$label.txt 2>&1; echo pytest-exit=\$? >> /out/$label.txt"
  echo "queue after: $(condor_q -allusers -totals 2>/dev/null | grep 'Total for all users')" >> /out/$label.txt
  condor_rm -all >/dev/null 2>&1
  echo "LEG-DONE $label"
done < /p/$legs
echo POOL-DONE
