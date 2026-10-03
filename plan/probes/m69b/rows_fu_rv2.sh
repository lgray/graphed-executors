#!/bin/bash
# root inside m68b-minicondor:local: /src = PR tree 61034b3; /srcold, /srcmain = that tree with 5fdb3c0 / 3b02317 src (all ro).
# Pool config + pins as the m69b exec reviews; PR tree installed editable; the main leg runs from /workmain,
# whose pytest pythonpath puts /workmain/src first.
set -u
echo "MOUNT_UNDER_SCRATCH =" > /etc/condor/config.d/99-jobs-share-tmp
printf '%s\n' 'use feature : GPUs' 'GPU_DISCOVERY_EXTRA = $(GPU_DISCOVERY_EXTRA) -simulate:2,1' > /etc/condor/config.d/99-sim-gpu
/start.sh > /tmp/start.log 2>&1 &
for i in $(seq 120); do condor_status -schedd -af Name 2>/dev/null | grep -q . && condor_status -af Name 2>/dev/null | grep -q . && break; sleep 2; done
condor_status -af Name State Cpus Memory
export PATH=/root/.cargo/bin:$PATH
uv pip install --python /opt/venv/bin/python \
  "graphed[awkward,numpy] @ git+https://github.com/graphed-org/graphed@a51bee4ff0b40c33cd68cca593f8a74c11d9f516" \
  "graphed-histogram[histserv] @ git+https://github.com/graphed-org/graphed-histogram@3830acaa26a9a5860892f263c0b0ca8c96efadb8" \
  grpcio-health-checking 2>&1 | tail -2
for d in work workold workmain; do rm -rf /$d; done
cp -r /src /work && cp -r /srcold /workold && cp -r /srcmain /workmain && rm -f /work/.git /workold/.git /workmain/.git && chown -R submituser:submituser /work /workold /workmain
uv pip install --python /opt/venv/bin/python --no-deps -e /work 2>&1 | tail -1
ROWS="tests/extra/m69b/test_m69b_schedulable.py::test_a_later_plan_s_refusal_says_the_runner_s_pilots_keep_their_slots_until_it_closes
tests/extra/m69b/test_m69b_schedulable.py::test_a_first_plan_s_server_is_refused_where_only_its_set_s_earlier_server_holds_room
tests/extra/m69b/test_m69b_sibling_room.py::test_a_server_that_fits_only_where_its_set_s_earlier_one_runs_is_refused_naming_it"
run() {  # dir, label, pytest args
  su submituser -s /bin/bash -c "cd $1 && export PATH=/opt/venv/bin:\$PATH && \
    python -c 'import sys; sys.path.insert(0, \"src\"); import graphed_executors as g; print(\"imports\", g.__file__)' && \
    python -m pytest -p no:cacheprovider -q -rfEs -o faulthandler_timeout=300 ${*:3}" > /tmp/$2.txt 2>&1
  echo "== $2: exit=$?"; grep -E "^imports|passed|failed|^FAILED|^E +(assert|AssertionError)" /tmp/$2.txt | cut -c1-400
}
run /workmain main-rows $ROWS
run /workold old-rows $ROWS
grep -o "(cluster [0-9]*, held until [^)]*)" /tmp/old-rows.txt | sort -u
grep -o "beside [^:]*: [^;]*; [^']*" /tmp/main-rows.txt | sort -u | head -4
run /work pr-rows $ROWS
run /work pr-frozen7 tests/frozen/m69b/test_service_order.py::test_a_later_server_is_refused_where_only_its_runner_s_pilots_hold_room
echo "queue after: $(condor_q -allusers -totals 2>/dev/null | grep 'Total for all users')"
