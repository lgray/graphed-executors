"""m68b r22-B1 probe: the submit-side paths a ServiceJob spells, under a RELATIVE launcher.log_dir and a relative
input name, against executors c2298d7's CondorPilots (it keeps log_dir as given, launch.py __init__) and its _stage.

For three spellings of a service dir built as ServiceJob.files()/submit() would (env.tgz a file symlink in initialdir to
the pilots' env.tgz; the input `models` mirrored into service/ as file symlinks):
  rel       = every path spelled from launcher.log_dir and the input name as given (the M39 shape)
  abs       = every path spelled from os.path.abspath(launcher.log_dir) and os.path.abspath(<input>) (the plan)
  input-rel = as abs, but the input's link target spelled from the input name as given (the other member)
it prints the frozen leg's witnesses (os.path.isfile of the env.tgz link and of the mirrored input file, initialdir and
executable absolute) and the job's outcome on the pool (service.sh unpacks env.tgz and reads the input).

Run: htcondor/mini:25.13.2-el9 (container r22p-mini, removed), as submituser, from a fresh ~/r22b1-rel:
  /opt/venv/bin/python probe_r22_b1_relative_paths.py   (/opt/venv: htcondor 25.13.2 + executors c2298d7)
"""
import dataclasses
import os
import shutil
import time
from pathlib import Path

import htcondor2 as htc
from graphed_executors.htcondor_backend.launch import PILOT_MODULE, CondorPilots
from graphed_executors.htcondor_backend.sites import SITES

base = Path(os.path.expanduser("~/r22b1-rel"))
shutil.rmtree(base, ignore_errors=True)
base.mkdir()
os.chdir(base)
env = base / "venv"
(env / "bin").mkdir(parents=True)
(env / "pyvenv.cfg").write_text("home = /usr/bin\n")
Path("models").mkdir()
Path("models/m.txt").write_text("model\n")
pilots = CondorPilots(dataclasses.replace(SITES["generic"], ship_env=True), log_dir="logs", env=env)
Path(pilots.log_dir).mkdir()
pilots._stage(pilots.log_dir, "pilot.sh", PILOT_MODULE)
print("CondorPilots(log_dir='logs').log_dir = %r; _stage wrote %s: %s"
      % (str(pilots.log_dir), pilots.log_dir / "env.tgz", (pilots.log_dir / "env.tgz").is_file()))
schedd = htc.Schedd()
as_given = str
for case, spell, spell_input in (("rel", as_given, as_given), ("abs", os.path.abspath, os.path.abspath),
                                 ("input-rel", os.path.abspath, as_given)):
    d = Path(spell(pilots.log_dir)) / ("service-" + case)
    (d / "service" / "models").mkdir(parents=True)
    os.symlink(spell(pilots.log_dir / "env.tgz"), d / "env.tgz")
    os.symlink(spell_input(Path("models") / "m.txt"), d / "service" / "models" / "m.txt")
    (d / "service.sh").write_text("#!/bin/sh\ntar xzf env.tgz && ls -d env && cat service/models/m.txt\n")
    (d / "service.sh").chmod(0o755)
    desc = {"executable": str(d / "service.sh"), "initialdir": str(d), "transfer_input_files": "env.tgz,service",
            "should_transfer_files": "YES", "output": "service.out", "error": "service.err", "log": "service.log",
            "request_memory": "16"}
    print("%s: isfile(<initialdir>/env.tgz) %s | isfile(<initialdir>/service/models/m.txt) %s | initialdir absolute %s"
          " | executable absolute %s" % (case, os.path.isfile(d / "env.tgz"), os.path.isfile(d / "service/models/m.txt"),
                                         os.path.isabs(desc["initialdir"]), os.path.isabs(desc["executable"])))
    cl = schedd.submit(htc.Submit(desc)).cluster()
    ad = None
    for _ in range(90):
        q = schedd.query(f"ClusterId == {cl}", ["JobStatus", "HoldReasonCode", "HoldReason"])
        if q and q[0].get("JobStatus") == 5:
            ad = dict(q[0])
            break
        if not q:
            ad = dict(next(iter(schedd.history(f"ClusterId == {cl}", ["JobStatus", "ExitCode"], match=1)), {}))
            break
        time.sleep(1)
    out = (d / "service.out").read_text().split() if (d / "service.out").exists() else None
    print("   job: %s; service.out %s" % ({k: ad.get(k) for k in ("JobStatus", "ExitCode", "HoldReasonCode")}
                                         if ad else None, out))
    if ad and ad.get("HoldReason"):
        print("   HoldReason:", ad["HoldReason"][ad["HoldReason"].find("first failure"):])
    schedd.act(htc.JobAction.Remove, f"ClusterId == {cl}")
