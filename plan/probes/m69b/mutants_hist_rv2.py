"""Round-1 mutants plus delta mutants, run WITHOUT -x against each worktree in argv[1:-1] (old frozen
b3a6a84, refrozen 6ddb1b1); argv[-1] is the python. Prints, per mutant and worktree, the failing
rows of the rewritten files, so a row that stopped discriminating shows as a lost kill."""
import os, re, subprocess, sys
from pathlib import Path

R1 = Path(__file__).with_name("mutants_hist_rv1.py").read_text()
ns: dict = {"__file__": __file__}
exec(R1[: R1.index("results = []")].replace("WT = Path(sys.argv[1]); PY = sys.argv[2]; ONLY = set(sys.argv[3:])", ""), ns)
HS, F = ns["HS"], ns["F"]
MUTANTS = ns["MUTANTS"] + [
  ("stale-B", HS, "_BASE = 164 * MiB", "_BASE = 129 * MiB", []),
  ("stale-b", HS, "_FILL_B = 3.5", "_FILL_B = 3.0", []),
  ("ffd-reversed-tie", HS, "key=lambda s: (-s[3].stored, str(s[0]))", "key=lambda s: (-s[3].stored, [-ord(c) for c in str(s[0])])", []),
  ("drop-fill-b-workers", HS, "(_FILL_A + _FILL_B * workers) * m", "(_FILL_A + _FILL_B) * m", []),
  ("below-B-accepted", HS, "if offered[0] * MiB < _BASE:", "if offered[0] * MiB < _BASE - MiB:", []),
]
REWRITTEN = [F + "test_histserv_packing.py", F + "test_histserv_fill_path.py", F + "test_histserv_surface.py"]
*WTS, PY = sys.argv[1:]
for name, rel, old, new, tests in MUTANTS:
    row = []
    for wt in map(Path, WTS):
        path = wt / rel; text = path.read_text()
        if text.count(old) != 1:
            row.append("n/a"); continue
        try:
            path.write_text(text.replace(old, new))
            r = subprocess.run([PY, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", "-o", "addopts=", *dict.fromkeys(tests + REWRITTEN)],
                               cwd=wt, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(wt / "src")})
        finally:
            path.write_text(text)
        fails = sorted({re.sub(r" - .*", "", l[7:]).split("::", 1)[1][:60] for l in r.stdout.splitlines() if l.startswith("FAILED ")})
        row.append(("KILLED" if r.returncode else "SURVIVED") + " " + ",".join(fails))
    print(f"{name:26s}", " || ".join(row), flush=True)
for wt in WTS:
    print("diff", wt[-12:], repr(subprocess.run(["git", "diff", "--stat"], cwd=wt, capture_output=True, text=True).stdout))
