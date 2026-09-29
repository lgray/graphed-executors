"""m68b r22-B1 review probe: a relative ``log_dir`` resolved at a later cwd than the one ``CondorPilots.start`` used.

``HTCondorBackend.__init__`` calls ``launcher.start`` (backend.py), which ``_stage``s ``env.tgz`` into ``log_dir`` as
given (relative, launch.py ``CondorPilots.__init__``), on c2298d7 and on 0e48380 alike; ``host_service`` runs later,
once per run. The plan spells the
``service-<key>/`` dir and the ``env.tgz`` link target from ``os.path.abspath(launcher.log_dir)`` at ServiceJob time.
This probe runs the real ``CondorPilots.start`` from cwd A, removes its pilot cluster, then changes cwd and spells
the service dir the plan's way, and submits a job whose ``service.sh`` unpacks ``env.tgz`` and prints the env's marker:
  plan/B-empty  cwd B without logs/: the service dir cannot be created where the plan puts it (parents are made to
                go on), and the env.tgz link dangles
  plan/B-other  cwd B holding another runner's logs/env.tgz: the link resolves, to that other env
  control       the same after cwd B, spelled from os.path.abspath(log_dir) captured when start() returned (cwd A)

Run: htcondor/mini:25.13.2-el9, as submituser, /opt/venv/bin/python probe_r22r_b1_cwd_between_runs.py, with /opt/venv
(python 3.12, htcondor 25.13.2) holding executors c2298d7 (container r22r-mini) and then executors 0e48380 + graphed
d0ad16b (container r22r-mini2); both removed, both outputs in the .txt.
"""
import dataclasses
import io
import os
import shutil
import tarfile
import time
from pathlib import Path

import htcondor2 as htc
from graphed_executors.htcondor_backend.launch import CondorPilots
from graphed_executors.htcondor_backend.sites import SITES

home = Path(os.path.expanduser("~"))
A, B = home / "r22r-a", home / "r22r-b"
for d in (A, B):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()


def fake_venv(root, marker):
    (root / "bin").mkdir(parents=True)
    (root / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (root / "marker.txt").write_text(marker + "\n")
    return root


os.chdir(A)
pilots = CondorPilots(dataclasses.replace(SITES["generic"], ship_env=True), log_dir="logs",
                      env=fake_venv(A / "venv", "env-of-A"))
pilots.start("http://127.0.0.1:1", b"\0" * 32, 1)
schedd = htc.Schedd()
schedd.act(htc.JobAction.Remove, f"ClusterId == {pilots.cluster[1]}")
at_start = os.path.abspath(pilots.log_dir)
print("start() from %s: log_dir %r, env.tgz written %s" % (A, str(pilots.log_dir), (A / "logs/env.tgz").is_file()))


def submit(d, target, case):
    (d / "service").mkdir()
    os.symlink(target, d / "env.tgz")
    (d / "service.sh").write_text("#!/bin/sh\ntar xzf env.tgz && cat env/marker.txt\n")
    (d / "service.sh").chmod(0o755)
    desc = {"executable": str(d / "service.sh"), "initialdir": str(d), "transfer_input_files": "env.tgz,service",
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
    out = (d / "service.out").read_text().split() if (d / "service.out").exists() else None
    print("%-12s dir %s | link -> %s | isfile %s | job %s | service.out %s"
          % (case, d, target, os.path.isfile(d / "env.tgz"),
             {k: ad.get(k) for k in ("JobStatus", "ExitCode", "HoldReasonCode")} if ad else None, out))
    schedd.act(htc.JobAction.Remove, f"ClusterId == {cl}")


os.chdir(B)  # e.g. a notebook's %cd between building the runner and a later run
d = Path(os.path.abspath(pilots.log_dir)) / "service-plan-empty"
try:
    d.mkdir(exist_ok=False)
except FileNotFoundError as exc:
    print("plan/B-empty mkdir(exist_ok=False):", repr(exc))
    d.mkdir(parents=True)
submit(d, os.path.join(os.path.abspath(pilots.log_dir), "env.tgz"), "plan/B-empty")
shutil.rmtree(B / "logs")

(B / "logs").mkdir()
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    info = tarfile.TarInfo("env/marker.txt")
    data = b"env-of-another-runner\n"
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
(B / "logs/env.tgz").write_bytes(buf.getvalue())
d = Path(os.path.abspath(pilots.log_dir)) / "service-plan-other"
d.mkdir(exist_ok=False)
submit(d, os.path.join(os.path.abspath(pilots.log_dir), "env.tgz"), "plan/B-other")

d = Path(at_start) / "service-control"
d.mkdir(exist_ok=False)
submit(d, os.path.join(at_start, "env.tgz"), "control")
