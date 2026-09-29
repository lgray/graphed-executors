"""m68b r22-B1 probe (POSIX, stdlib, no condor): which witnesses tell announce.py's resolved {python} apart from its
own sys.executable on Linux and macOS, with framework and non-framework harness interpreters?

Runs announce_proto.py and three mutants of its {python} line:
  A  python = sys.executable
  B  a name with a separator made absolute, a bare name -> sys.executable (the S-05 case alone)
  C  python = cfg["python"] (left as given)
on the B1 row's two {python} legs (attached, url on a closed port, lease_s 3; "ready" = the self-check passed):
  leg 1  PATH removed from the env, {python} = bare "python3"; argv {python} rec.py {port} <file>, rec.py (an input
         in service/) writes its own sys.executable to <file>, then serves.
         rec  = that record == P, the sys.executable the defpath python3 prints when run without PATH (the plan's
                witness; the leg runs only when P is absolute and != the harness's sys.executable)
         ps   = `ps -o args=` argv[0] of the logged ready pid != the harness's sys.executable (r21's proposal)
         ps== = that argv[0] == shutil.which("python3", path=os.defpath) (r21's Linux-only addition)
  leg 2  {python} = ./env/bin/python, an sh script in the job dir that writes a marker file, then
         `exec <sys.executable> "$@"`; witness: ready and the marker exists.
Leg 1's precondition is printed: the defpath python3, P, and whether the leg would run.

Run, per harness interpreter:  <python> probe_r22_b1_python_witness.py
  Linux: htcondor/mini:25.13.2-el9 (container r22p-mini, removed), /opt/venv/bin/python (uv 3.12) and
         /usr/bin/python3 (3.9.25, which is the defpath python3 there).
  macOS 26 arm64 (the planner's host): uv python 3.12 (non-framework), Homebrew python3.14 (framework build) and
         /usr/bin/python3 (the CLT shim, the defpath python3 there).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = '''        python = (os.path.abspath(cfg["python"]) if os.sep in cfg["python"]
                  else shutil.which(cfg["python"], path=os.environ.get("PATH", os.defpath)) or cfg["python"])'''
MUTANTS = {
    "proto": OLD,
    "A": "        python = sys.executable",
    "B": '        python = os.path.abspath(cfg["python"]) if os.sep in cfg["python"] else sys.executable',
    "C": '        python = cfg["python"]',
}
REC = ("import sys, runpy\nopen(sys.argv[2], 'w').write(sys.executable)\n"
       "sys.argv = ['http.server', sys.argv[1]]\nrunpy.run_module('http.server', run_name='__main__')\n")


def free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run(script, python, drop_path, argv):
    d = tempfile.mkdtemp(prefix="r22b1-job-")
    os.makedirs(os.path.join(d, "env", "bin"))
    os.makedirs(os.path.join(d, "service"))
    open(os.path.join(d, "service", "rec.py"), "w").write(REC)
    wrapper = os.path.join(d, "env", "bin", "python")
    open(wrapper, "w").write('#!/bin/sh\necho ran > "%s"\nexec "%s" "$@"\n' % (os.path.join(d, "marker"), sys.executable))
    os.chmod(wrapper, 0o755)
    open(os.path.join(d, "graphed-secret"), "w").write("00" * 32)
    port = free_port()
    json.dump({"argv": [a.replace("REC", os.path.join(d, "record")) for a in argv], "env": {}, "check": "http:/",
               "ports": [port, port], "key": "k", "url": "http://127.0.0.1:1", "watch": None, "python": python,
               "timeout_s": 20, "lease_s": 3, "beat_s": 1}, open(os.path.join(d, "svc.json"), "w"))
    env = dict(os.environ)
    if drop_path:
        env.pop("PATH", None)
    p = subprocess.Popen([sys.executable, script, "svc.json"], cwd=d, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    argv0, ready = None, False
    for line in p.stdout:
        m = re.search(r"ready pid=(\d+)", line)
        if m:
            ready = True
            out = subprocess.run(["ps", "-o", "args=", "-p", m.group(1)], capture_output=True, text=True).stdout
            argv0 = out.split()[0] if out.split() else None
    p.wait()
    rec = os.path.join(d, "record")
    record = open(rec).read() if os.path.exists(rec) else None
    marker = os.path.exists(os.path.join(d, "marker"))
    shutil.rmtree(d)
    return ready, argv0, record, marker, d


src = open(os.path.join(HERE, "announce_proto.py")).read()
assert OLD in src
tmp = tempfile.mkdtemp(prefix="r22b1-")
defpy = shutil.which("python3", path=os.defpath)
noenv = {k: v for k, v in os.environ.items() if k != "PATH"}
P = defpy and subprocess.run([defpy, "-c", "import sys; print(sys.executable)"], env=noenv, capture_output=True,
                             text=True).stdout.strip()
print("%s | python %s | harness sys.executable %s | defpath python3 %s prints P = %r | leg 1 runs: %s"
      % (sys.platform, sys.version.split()[0], sys.executable, defpy, P,
         bool(P) and os.path.isabs(P) and P != sys.executable))
for name, line in MUTANTS.items():
    script = os.path.join(tmp, name + ".py")
    open(script, "w").write(src.replace(OLD, line))
    ready, argv0, record, _, _ = run(script, "python3", True, ["{python}", "rec.py", "{port}", "REC"])
    rec_ok = record == P
    print("  %-5s leg 1: ready %-5s rec %-5s ps %-5s ps== %-5s | record %r | ps argv[0] %s"
          % (name, ready, rec_ok, argv0 is not None and argv0 != sys.executable, argv0 == defpy, record, argv0))
    ready, argv0, _, marker, _ = run(script, "./env/bin/python", False, ["{python}", "-m", "http.server", "{port}"])
    print("  %-5s leg 2: ready %-5s marker %-5s -> %s" % (name, ready, marker, "PASS" if ready and marker else "FAIL"))
shutil.rmtree(tmp)
