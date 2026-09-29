"""m68b r23-B1 probe: which half of the in-process L17 leg needs Unix-only names.

The prototype's SIGTERM path (`main()` with `serve` raising `_Stop`), with `os.kill` spied and the names typeshed marks
Unix-only (`os.WNOHANG`, `signal.SIGKILL`, `signal.pthread_sigmask`) deleted, as on Windows:
  reaped    `CHILD[0]` a Popen already waited on: expected exit 143, no os.kill call, no Unix-only name touched
  control   an unreaped child: signalled once, then the pid reap reaches a Unix-only name (AttributeError)
Run (macOS arm64): uv run --no-project --python 3.9 python probe_r23_b1_l17_nonposix.py
"""
import importlib.util
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("announce_proto", os.path.join(HERE, "announce_proto.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.log = lambda msg: None
UNIX_ONLY = [(os, "WNOHANG"), (signal, "SIGKILL"), (signal, "pthread_sigmask")]


def raise_stop():
    raise mod._Stop


def stop_path(child):
    saved = {(m, n): getattr(m, n) for m, n in UNIX_ONLY}
    prev, orig_kill, orig_serve = signal.getsignal(signal.SIGTERM), os.kill, mod.serve
    kills = []
    mod.CHILD[0] = child
    mod.serve = raise_stop
    os.kill = lambda pid, sig: kills.append(sig)
    for m, n in saved:
        delattr(m, n)
    try:
        mod.main()
        outcome = "returned"
    except SystemExit as exc:
        outcome = "exit %s" % exc.code
    except AttributeError as exc:
        outcome = "AttributeError: %s" % exc
    finally:
        for (m, n), v in saved.items():
            setattr(m, n, v)
        os.kill, mod.serve = orig_kill, orig_serve
        signal.signal(signal.SIGTERM, prev)
    return outcome, kills


reaped = subprocess.Popen([sys.executable, "-c", "pass"])
reaped.wait()
print("reaped  :", *stop_path(reaped))
live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
print("control :", *stop_path(live))
live.kill()
live.wait()
print("python", sys.version.split()[0], sys.platform)
