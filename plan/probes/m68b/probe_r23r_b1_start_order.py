"""m68b r23-B1 review probe: the round-17 line in `CondorPilots.start` against `start`'s own refusals (`_refuse`:
image, sandbox root) and its `mkdtemp` under `_sandbox()`, on executors 0e48380 plus that one line. Refusals raise
before the bindings; an accepted start is stopped at `_htcondor` (fake), after the line and the writes.

  O1  sandbox root R, relative log_dir="logs" from a cwd inside R: accepted, log_dir == abspath at start's cwd
  O2  the same from a cwd outside R: refused naming log_dir, nothing created under that cwd
  O3  log_dir=None on a profile needing an image, no image: refused, no new mkdtemp dir under R
  O4  log_dir=None, accepted: a fresh absolute dir under R holding the secret
Run: container r23r-mini (htcondor/mini:25.13.2-el9, removed), as submituser, /opt/venv/bin/python 3.12.14,
PYTHONPATH=/code/src (scratch worktree of executors 0e48380 + the line):  python probe_r23r_b1_start_order.py
"""
import dataclasses
import getpass
import os
import shutil
from pathlib import Path

import graphed_executors.htcondor_backend.launch as launch
from graphed_executors.htcondor_backend.launch import CondorPilots
from graphed_executors.htcondor_backend.sites import SITES

base = Path(os.path.expanduser("~")) / "r23r-order"
shutil.rmtree(base, ignore_errors=True)
R, out = base / "root", base / "outside"
(R / getpass.getuser() / "cwd").mkdir(parents=True)
out.mkdir()
profile = dataclasses.replace(SITES["generic"], sandbox_root=str(R / "{user}"), ship_env=False)


class Stop(Exception):
    pass


def stop():
    raise Stop


launch._htcondor = stop


def start(p):
    try:
        p.start("http://127.0.0.1:1", b"\0" * 32, 1)
    except Stop:
        return "reached bindings"
    except ValueError as exc:
        return f"refused: {exc}"


inside = R / getpass.getuser() / "cwd"
os.chdir(inside)
p = CondorPilots(profile, log_dir="logs")
print(f"O1 {start(p)} | log_dir {str(p.log_dir)!r} == abspath at start {str(p.log_dir) == str(inside / 'logs')}"
      f" | secret {(inside / 'logs/graphed-secret').is_file()}")
os.chdir(out)
p = CondorPilots(profile, log_dir="logs")
print(f"O2 {start(p)} | log_dir {str(p.log_dir)!r} | created under cwd {sorted(os.listdir(out))}")
before = sorted(os.listdir(R / getpass.getuser()))
p = CondorPilots(dataclasses.replace(profile, submit={"MY.SingularityImage": '"{image}"'}))
print(f"O3 {start(p)} | log_dir {p.log_dir} | new dirs under R {sorted(set(os.listdir(R / getpass.getuser())) - set(before))}")
p = CondorPilots(profile)
print(f"O4 {start(p)} | log_dir {str(p.log_dir)!r} absolute {p.log_dir.is_absolute()} under R "
      f"{p.log_dir.is_relative_to(R)} | secret {(p.log_dir / 'graphed-secret').is_file()}")
