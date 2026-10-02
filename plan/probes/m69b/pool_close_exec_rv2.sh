#!/bin/bash
# host side: run probe_close_pool_exec_rv2.py in the m69b-exec-rv2-pool container as submituser; args: SRC CASE [POLL_S]
src=$1; shift
echo "=== src=$src case=$*"
docker exec m69b-exec-rv2-pool su submituser -s /bin/bash -c "cd /work && export PATH=/opt/venv/bin:\$PATH PYTHONPATH=$src:tests/frozen/m68b && timeout 900 python -u /probes/probe_close_pool_exec_rv2.py $*" 2>&1 | grep -v Warning | grep -v '^\s*$'
