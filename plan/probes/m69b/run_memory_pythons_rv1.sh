#!/bin/sh
# m69b-r1 review: the planner's probe_histserv_memory.py, unchanged, on the CI legs' other Pythons (native arch).
#   ./run_memory_pythons_rv1.sh > probe_memory_pythons_rv1.txt
cd "$(dirname "$0")" || exit 1
for py in 3.11 3.13 3.14; do
  echo "=== python:$py-slim"
  docker run --rm --name "m69b-rv1-mem-$py" -v "$PWD:/p" "python:$py-slim" sh -c \
    'pip install -q --root-user-action=ignore "histserv==0.2.1" psutil >/dev/null 2>&1 && uname -m && python /p/probe_histserv_memory.py' \
    2> /dev/null
done
