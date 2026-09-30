#!/bin/sh
# Regenerates the histserv 0.2.1 memory figures (histserv from PyPI, python:3.12-slim Linux container):
#   ./run_memory_probe.sh        > probe_histserv_memory.txt        (the host's arch, native)
#   ./run_memory_probe.sh amd64  > probe_histserv_memory.amd64.txt  (x86_64; emulated on an arm64 host)
cd "$(dirname "$0")" || exit 1
arch=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/'); [ "$1" = amd64 ] && arch=amd64
docker run --rm --platform "linux/$arch" -v "$PWD:/p" python:3.12-slim sh -c \
  'pip install -q --root-user-action=ignore "histserv==0.2.1" psutil >/dev/null 2>&1 && uname -m && python /p/probe_histserv_memory.py' \
  2> /dev/null
