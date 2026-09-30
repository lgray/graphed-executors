#!/bin/sh
# m69b-r3: which frozen graphed-histogram tests depend on `_refuse_shortfall`? The frozen suite, once as is and
# once with the refusal a no-op (probe_refuse_shortfall_plugin_rv3.py); the failing sets are compared.
# Run: sh run_refuse_shortfall_rv3.sh > probe_refuse_shortfall_rv3.txt 2>&1
H=~/vibe-coding/cloud/graphed-histogram
P=$(cd "$(dirname "$0")" && pwd)
cd "$H" || exit 1
export PYTHONDONTWRITEBYTECODE=1
for leg in baseline noop; do
  extra=""; [ "$leg" = noop ] && extra="-p probe_refuse_shortfall_plugin_rv3"
  PYTHONPATH="$P" .venv/bin/python -m pytest tests/frozen -o addopts= -q -p no:cacheprovider -p no:randomly $extra -rf 2>&1 \
    | grep -E "^FAILED|passed|failed" | sed "s/^/$leg: /"
done
