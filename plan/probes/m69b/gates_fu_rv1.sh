#!/bin/zsh
# macOS gates at 5fdb3c0 (scratch worktree), venv tools, tree src first.
S=${0:a:h}; T=$S/fu-rv1; V=/Users/lgray/vibe-coding/cloud/.venv-m69b/bin
cd $T; export PYTHONPATH=$T/src
echo "== head $(git rev-parse --short HEAD)"
echo "== ruff check"; $V/ruff check . ; echo "exit=${pipestatus[1]}"
echo "== ruff format --check"; $V/ruff format --check . | tail -2; echo "exit=${pipestatus[1]}"
echo "== mypy (pyproject strict, files=src tests examples)"; $V/mypy 2>&1 | tail -3; echo "exit=${pipestatus[1]}"
echo "== mypy --platform win32"; $V/mypy --platform win32 2>&1 | tail -3; echo "exit=${pipestatus[1]}"
echo "== sphinx -W"; $V/sphinx-build -W -q -b html docs $S/out/docs-html 2>&1 | tail -5; echo "exit=${pipestatus[1]}"
echo "== pytest extra + frozen m68a/m68b/m69b"
$V/python -m pytest -q -p no:cacheprovider tests/extra tests/frozen/m68a tests/frozen/m68b tests/frozen/m69b -o faulthandler_timeout=300 > $S/out/pytest_mac.txt 2>&1; echo "exit=${pipestatus[1]}"
tail -3 $S/out/pytest_mac.txt
