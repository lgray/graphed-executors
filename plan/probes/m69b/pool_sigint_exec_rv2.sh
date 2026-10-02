#!/bin/bash
# inside the container as root: start probe_sigint_exec_rv2.py as submituser, SIGINT it after its first wait log,
# then report its exit, how long the interrupt took, and the queue.
cd /work
su submituser -s /bin/bash -c "cd /work && PATH=/opt/venv/bin:\$PATH PYTHONPATH=/work/src:tests/frozen/m69b:tests/frozen/m68a exec python -u /probes/probe_sigint_exec_rv2.py" > /tmp/rv2-sigint.log 2>&1 &
for i in $(seq 300); do grep -q 'waits for a slot' /tmp/rv2-sigint.log && break; sleep 1; done
pid=$(pgrep -u submituser -f probe_sigint_exec_rv2.py | head -1)
echo "wait logged after ${i}s; SIGINT to $pid"; t=$(date +%s); kill -INT "$pid"
for j in $(seq 300); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
wait; echo "exit=$? ${j}s after SIGINT ($(( $(date +%s) - t ))s)"
grep -v Warning /tmp/rv2-sigint.log | grep -E 'waits for a slot|Interrupt|Error|run returned|^[0-9.]+s:' | cut -c1-220
sleep 3; condor_q -allusers -totals | grep 'all users'; condor_history -limit 3 -af ClusterId JobBatchName JobStatus NumJobStarts
