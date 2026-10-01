#!/bin/sh
# Regenerates the histserv 0.2.1 memory figures on the CI Pythons 3.11-3.14 (histserv from PyPI, python:3.1x-slim Linux):
#   ./run_memory_probe.sh        > probe_histserv_memory.txt        (the host's arch, native)
#   ./run_memory_probe.sh amd64  > probe_histserv_memory.amd64.txt  (x86_64; emulated on an arm64 host)
#   PYS="3.13 3.14" limits the Pythons
#   SCEN=connections ./run_memory_probe.sh [amd64] > probe_histserv_connections[.amd64].txt   (K alone)
cd "$(dirname "$0")" || exit 1
arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/'); [ "$1" = amd64 ] && arch=amd64
for py in ${PYS:-3.11 3.12 3.13 3.14}; do
  echo "=== python:$py-slim linux/$arch"
  docker run --rm --name "m69b-mem-$arch-$py" --platform "linux/$arch" -e SCEN -v "$PWD:/p" "python:$py-slim" sh -c \
    'pip install -q --root-user-action=ignore "histserv==0.2.1" psutil >/dev/null 2>&1 && uname -m && python /p/probe_histserv_memory.py $SCEN' \
    2> /dev/null
done
