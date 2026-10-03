# The local precommit's integrity check over the PR as it stood before commit (worktree 5fdb3c0 vs HEAD 3b02317),
# then the same check over a control diff that keeps the dropped assert line.
import subprocess, sys
from pathlib import Path
from graphed_orchestrator.precommit import check_integrity
from graphed_orchestrator.integrity import scan_diff
repo = Path(sys.argv[1])
print("check_integrity:", check_integrity(repo))
diff = subprocess.run(["git", "diff", "HEAD"], cwd=repo, capture_output=True, text=True).stdout
kept = diff.replace('-        assert self.cluster is not None, "matched only once submitted"\n', ' ' * 9 + 'assert self.cluster is not None, "matched only once submitted"\n')
print("scan, as is:      ", scan_diff(diff))
print("scan, assert kept:", scan_diff(kept), "(control: the line was in the diff)", kept != diff)
