"""m68b r23-B1 probe: the M40 cut, ``CondorPilots.start`` storing ``log_dir`` absolute, on executors 0e48380.

Three trees of executors 0e48380, the one on PYTHONPATH named by argv[1]:
  base   unchanged (``CondorPilots.__init__`` keeps ``Path(log_dir)``)
  start  ``start`` replaces its ``mkdtemp`` default with
         ``self.log_dir = Path(os.path.abspath(self.log_dir or tempfile.mkdtemp(...)))``
  init   ``__init__`` stores ``Path(os.path.abspath(log_dir))``
Cases (the service dir and ``env.tgz`` link spelled from ``launcher.log_dir`` itself, as the plan now spells them):
  R  start() from A with log_dir="logs"; chdir B holding its own logs/env.tgz and logs/graphed-secret; spell
     service-<key>/ and its env.tgz link, submit a job that unpacks env.tgz and prints the env's marker; then
     pilots.stop() from B: which graphed-secret it unlinks.
  P  constructed in A, start() from C: env.tgz is written under C; from D, does log_dir name where it was written?
  Q  log_dir assigned after construction (driverless assigns launcher.log_dir), start() from A: from B, does
     log_dir name where env.tgz was written?

Run: htcondor/mini:25.13.2-el9 (container r23p-mini, removed), as submituser, /opt/venv/bin/python 3.12 with
htcondor 25.13.2 and graphed d0ad16b, PYTHONPATH=/r23/code-<tree>/src, once per tree:
  python probe_r23_b1_logdir_abs.py <tree>
"""
import dataclasses
import io
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path

import htcondor2 as htc
import graphed_executors.htcondor_backend.launch as launch
from graphed_executors.htcondor_backend.launch import CondorPilots
from graphed_executors.htcondor_backend.sites import SITES

tree = sys.argv[1]
print(f"# tree {tree}: launch.py from {launch.__file__}")
root = Path(os.path.expanduser("~")) / f"r23-{tree}"
shutil.rmtree(root, ignore_errors=True)
A, B, C, D = (root / n for n in "ABCD")
for d in (A, B, C, D):
    d.mkdir(parents=True)
schedd = htc.Schedd()
SITE = dataclasses.replace(SITES["generic"], ship_env=True)


def fake_venv(where, marker):
    (where / "bin").mkdir(parents=True)
    (where / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (where / "marker.txt").write_text(marker + "\n")
    return where


def make(log_dir, cwd, env):
    os.chdir(cwd)
    return CondorPilots(SITE, log_dir=log_dir, env=env)


def run_start(p, cwd):
    os.chdir(cwd)
    p.start("http://127.0.0.1:1", b"\0" * 32, 1)
    schedd.act(htc.JobAction.Remove, f"ClusterId == {p.cluster[1]}")


def submit(d, target):
    os.symlink(target, d / "env.tgz")
    (d / "service.sh").write_text("#!/bin/sh\ntar xzf env.tgz && cat env/marker.txt\n")
    (d / "service.sh").chmod(0o755)
    desc = {"executable": str(d / "service.sh"), "initialdir": str(d), "transfer_input_files": "env.tgz",
            "should_transfer_files": "YES", "output": "service.out", "error": "service.err", "log": "service.log",
            "request_memory": "16"}
    cl = schedd.submit(htc.Submit(desc)).cluster()
    ad = None
    for _ in range(90):
        q = schedd.query(f"ClusterId == {cl}", ["JobStatus", "HoldReasonCode"])
        if q and q[0].get("JobStatus") == 5:
            ad = dict(q[0])
            break
        if not q:
            ad = dict(next(iter(schedd.history(f"ClusterId == {cl}", ["JobStatus", "ExitCode"], match=1)), {}))
            break
        time.sleep(1)
    schedd.act(htc.JobAction.Remove, f"ClusterId == {cl}")
    out = (d / "service.out").read_text().split() if (d / "service.out").exists() else None
    return {k: ad.get(k) for k in ("JobStatus", "ExitCode", "HoldReasonCode") if ad and ad.get(k) is not None}, out


def same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError as exc:
        return f"{type(exc).__name__}"


# R: the reviewer's case, then the pilots' own secret
p = make("logs", A, fake_venv(A / "venv", "env-of-A"))
run_start(p, A)
os.chdir(B)
(B / "logs").mkdir()
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    info = tarfile.TarInfo("env/marker.txt")
    data = b"env-of-another-runner\n"
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
(B / "logs/env.tgz").write_bytes(buf.getvalue())
(B / "logs/graphed-secret").write_text("another runner's\n")
d = Path(p.log_dir) / "service-k"
try:
    d.mkdir(exist_ok=False)
    made = "made"
except OSError as exc:
    made = type(exc).__name__
    d.mkdir(parents=True)
initialdir = os.path.abspath(d)  # what condor records for a relative initialdir submitted from B
job, out = submit(Path(initialdir), str(Path(p.log_dir) / "env.tgz"))
print(f"R log_dir {str(p.log_dir)!r} | mkdir {made} | initialdir under A/logs {Path(initialdir).is_relative_to(A / 'logs')}"
      f" | samefile(<initialdir>/env.tgz, A/logs/env.tgz) {same(Path(initialdir) / 'env.tgz', A / 'logs/env.tgz')}"
      f" | job {job} | service.out {out}")
p.stop()
print(f"R stop() from B: A/logs/graphed-secret exists {(A / 'logs/graphed-secret').exists()}"
      f" | B/logs/graphed-secret exists {(B / 'logs/graphed-secret').exists()}")

# P: constructed in A, started from C
shutil.rmtree(A / "logs")
p = make("logs", A, fake_venv(A / "venvP", "P"))
run_start(p, C)
written = [q for q in (A / "logs/env.tgz", C / "logs/env.tgz") if q.exists()]
os.chdir(D)
print(f"P env.tgz written under {[w.parent.parent.name for w in written]} | from D log_dir {str(p.log_dir)!r}"
      f" names it {[same(Path(p.log_dir) / 'env.tgz', w) for w in written]}")
p.stop()

# Q: log_dir assigned after construction, started from A
shutil.rmtree(A / "logs", ignore_errors=True)
p = make(None, A, fake_venv(A / "venvQ", "Q"))
p.log_dir = Path("logs")
run_start(p, A)
os.chdir(B)
print(f"Q from B log_dir {str(p.log_dir)!r} names A/logs/env.tgz {same(Path(p.log_dir) / 'env.tgz', A / 'logs/env.tgz')}")
p.stop()
