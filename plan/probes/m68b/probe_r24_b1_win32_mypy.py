"""m68b round-18 probe: the guarded `announce_proto.py` under `mypy --strict --platform win32` and `--platform linux`.

  G  the prototype as committed: Unix-only uses ([attr-defined]) per platform, and whether any error differs between
     the two platforms (the prototype is unannotated, so --strict's untyped-def/call errors are expected on both; their codes are listed)
  C  control, the same invocation on the pre-guard prototype (`git show ae932a8:plan/probes/m68b/announce_proto.py`)
Run (macOS, from plan/probes/m68b):
  uv run --no-project --python 3.12 --with mypy==2.3.1 python probe_r24_b1_win32_mypy.py > probe_r24_b1_win32_mypy.txt
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MYPY = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.12", "--no-incremental"]


def errors(path, plat, cwd):
    out = subprocess.run(MYPY + ["--platform", plat, path], cwd=cwd, capture_output=True, text=True).stdout
    return [re.sub(r"^.*?:(\d+):", r"\1:", line) for line in out.splitlines() if "error:" in line]


def report(tag, path, cwd):
    by = {plat: errors(path, plat, cwd) for plat in ("win32", "linux")}
    for plat, errs in by.items():
        unix = [e for e in errs if "[attr-defined]" in e]
        print(f"{tag} {plat:6s}: {len(errs)} errors, {len(unix)} attr-defined", [e.split(" error: ")[0] + " " +
              re.search(r'attribute "(\w+)"', e).group(1) for e in unix])
    codes = sorted({re.search(r"\[([\w-]+)\]$", e).group(1) for e in by["linux"]})
    print(f"{tag} error codes on linux: {codes}")
    print(f"{tag} errors only on win32: {sorted(set(by['win32']) - set(by['linux']))}")
    print(f"{tag} errors only on linux: {sorted(set(by['linux']) - set(by['win32']))}")


print(f"# mypy {subprocess.run([sys.executable, '-m', 'mypy', '--version'], capture_output=True, text=True).stdout.split()[1]}, "
      f"python {sys.version.split()[0]} ({sys.platform})")
with tempfile.TemporaryDirectory() as d:
    report("G", os.path.join(HERE, "announce_proto.py"), d)
    old = os.path.join(d, "announce_proto_ae932a8.py")
    with open(old, "w") as f:
        f.write(subprocess.run(["git", "show", "ae932a8:plan/probes/m68b/announce_proto.py"], cwd=HERE,
                               capture_output=True, text=True, check=True).stdout)
    report("C", old, d)
