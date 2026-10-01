"""Integrity shape scan over a git range (the precommit gate's scan_diff), with a positive control."""
import subprocess, sys
from graphed_orchestrator import precommit as pc
from graphed_orchestrator.integrity import scan_diff
repo, rng = sys.argv[1], sys.argv[2]
diff = subprocess.run(["git", "diff", rng, "--", "."], cwd=repo, capture_output=True, text=True, check=True).stdout
for label, text in (("range", diff), ("control", "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n+    pytest.skip('x')\n+    raise NotImplementedError\n")):
    f = scan_diff(text, protected_prefixes=(), config_hints=pc.DEFAULT_CONFIG_HINTS)
    print(label, len(f), [(x.code, x.path) for x in f][:20])
