#!/bin/zsh
# mypy --strict on services.py at 5fdb3c0 (no assert), per platform; control: one added use of self.cluster that needs narrowing.
S=${0:a:h}; T=$S/int-rv1; V=/Users/lgray/vibe-coding/cloud/.venv-m69b/bin; F=src/graphed_executors/htcondor_backend/services.py
cd $T; export PYTHONPATH=$T/src
for p in darwin linux win32; do
  echo "== --platform $p, as is"; $V/mypy --platform $p $F 2>&1 | tail -1
  cp $F $S/out/services.orig.py
  sed -i '' 's/^        ads = list(self.launcher._schedd.query(constraint=f"ClusterId == {self.cluster}"))$/&\n        _next = self.cluster + 1/' $F
  echo "-- control (added: _next = self.cluster + 1): $(grep -c '_next = self.cluster + 1' $F) line"; $V/mypy --platform $p $F 2>&1 | grep -E "error|Success" | head -2
  cp $S/out/services.orig.py $F
done
git diff --quiet 5fdb3c0 -- $F && echo "restored == 5fdb3c0"
