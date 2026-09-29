"""m68b r23-B1 review probe: `announce.py`'s Unix-only names under the `test` job's Windows `mypy --strict` (prek runs
mypy on every matrix OS, platform = the runner's), and which spellings pass on both platforms.

  P  the prototype `announce_proto.py`, `--platform win32` vs `linux`: every Unix-only name it uses (the population,
     from typeshed via mypy) and the function holding it
  F  three spellings of the pid reap: bare names; `# type: ignore[attr-defined]`; a `sys.platform` guard after the
     `pid is None` return (the in-process L17 leg's reaped path returns before it)
  T  a `skipif(sys.platform == "win32")` test body using a Unix-only name
Run: container r23r-mini (htcondor/mini:25.13.2-el9, removed), /opt/venv/bin/python 3.12.14 with mypy 2.3.1:
  python probe_r23r_b1_win32_mypy.py
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MYPY = [sys.executable, "-m", "mypy", "--python-version", "3.12", "--no-incremental"]
FILES = {
    "bare.py": "import os\nimport signal\n\n\ndef reap(pid: int) -> None:\n"
               "    os.waitpid(pid, os.WNOHANG)\n    os.kill(pid, signal.SIGKILL)\n",
    "ignore.py": "import os\nimport signal\n\n\ndef reap(pid: int) -> None:\n"
                 "    os.waitpid(pid, os.WNOHANG)  # type: ignore[attr-defined]\n"
                 "    os.kill(pid, signal.SIGKILL)  # type: ignore[attr-defined]\n",
    "guard.py": "import os\nimport signal\nimport sys\n\n\ndef reap(pid: int | None) -> None:\n"
                "    if pid is None or sys.platform == \"win32\":\n        return\n"
                "    os.waitpid(pid, os.WNOHANG)\n    os.kill(pid, signal.SIGKILL)\n",
    "test_skip.py": "import os\nimport sys\n\nimport pytest\n\n\n"
                    "@pytest.mark.skipif(sys.platform == \"win32\", reason=\"POSIX\")\n"
                    "def test_reap() -> None:\n    assert os.WNOHANG\n",
}


def mypy(args, cwd):
    out = subprocess.run(MYPY + args, cwd=cwd, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if "error:" in line or line.startswith("Success")]


proto = open(os.path.join(HERE, "announce_proto.py")).read().splitlines()


def holder(lineno):
    for i in range(lineno - 1, -1, -1):
        m = re.match(r"def (\w+)", proto[i])
        if m:
            return m.group(1)
    return "<module>"


with tempfile.TemporaryDirectory() as d:
    for plat in ("win32", "linux"):
        errs = [e for e in mypy(["--platform", plat, "--check-untyped-defs", os.path.join(HERE, "announce_proto.py")], d)
                if "attr-defined" in e]
        names = sorted({(int(e.split(":")[1]), re.search(r'attribute "(\w+)"', e).group(1)) for e in errs})
        print(f"P {plat}: {len(names)} Unix-only uses", [(n, f"{holder(ln)}:{ln}") for ln, n in names])
    for name, text in FILES.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(text)
        for plat in ("linux", "win32"):
            res = mypy(["--strict", "--platform", plat, name], d)
            print(f"{'T' if name.startswith('test') else 'F'} {name:13s} {plat:6s}",
                  "; ".join(sorted({r.split("error: ")[-1] if "error:" in r else r for r in res})))
