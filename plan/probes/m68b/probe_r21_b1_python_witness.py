"""m68b r21-B1 probe (local, POSIX, no condor): do the B1 row's {python} legs tell the resolved {python} apart from
announce.py's own sys.executable (the S-05 hazard: empty for a bare `python3` in a PATH-less job)?

Runs announce_proto.py and a mutant of it whose only change is `python = sys.executable`, each on the row's two legs:
  1. PATH removed from the env, {python} = bare "python3" (resolved on os.defpath);
  2. {python} = "./env/bin/python", a symlink in the job dir to this interpreter.
Prints the child's argv[0] (`ps -o args=` of the pid logged as `ready pid=<n>`), whether it is absolute (the row's
witness) and whether it equals the path the plan says {python} resolves to.

Run: python3 probe_r21_b1_python_witness.py > probe_r21_b1_python_witness.txt
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = '''        python = (os.path.abspath(cfg["python"]) if os.sep in cfg["python"]
                  else shutil.which(cfg["python"], path=os.environ.get("PATH", os.defpath)) or cfg["python"])'''


def scripts(tmp):
    src = open(os.path.join(HERE, "announce_proto.py")).read()
    assert OLD in src
    proto, mutant = os.path.join(tmp, "proto.py"), os.path.join(tmp, "mutant.py")
    open(proto, "w").write(src)
    open(mutant, "w").write(src.replace(OLD, "        python = sys.executable  # MUTANT"))
    return proto, mutant


def run(script, python, drop_path, port):
    d = tempfile.mkdtemp(prefix="r21b1-job-")
    os.makedirs(os.path.join(d, "env", "bin"))
    os.symlink(sys.executable, os.path.join(d, "env", "bin", "python"))
    open(os.path.join(d, "graphed-secret"), "w").write("00" * 32)
    json.dump({"argv": ["{python}", "-m", "http.server", "{port}"], "env": {}, "check": "http:/",
               "ports": [port, port + 1], "key": "k", "url": "http://127.0.0.1:1", "watch": None,
               "secret": "graphed-secret", "python": python, "timeout_s": 20, "lease_s": 3, "beat_s": 1},
              open(os.path.join(d, "svc.json"), "w"))
    env = dict(os.environ)
    if drop_path:
        env.pop("PATH", None)
    p = subprocess.Popen([sys.executable, script, "svc.json"], cwd=d, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    argv0 = None
    for line in p.stdout:
        m = re.search(r"ready pid=(\d+)", line)
        if m:
            argv0 = subprocess.run(["ps", "-o", "args=", "-p", m.group(1)], capture_output=True,
                                   text=True).stdout.split()[0]
    p.wait()
    shutil.rmtree(d)
    return argv0, d


tmp = tempfile.mkdtemp(prefix="r21b1-")
proto, mutant = scripts(tmp)
defpath_py = shutil.which("python3", path=os.defpath)
print("python", sys.version.split()[0], "| announce.py's sys.executable:", sys.executable,
      "| python3 on os.defpath:", defpath_py)
for name, script in (("proto", proto), ("mutant", mutant)):
    a, _ = run(script, "python3", True, 24600)
    print("%-6s leg 1 (PATH removed, python3): argv[0] %s | absolute %s | == os.defpath python3 %s | == sys.executable %s"
          % (name, a, os.path.isabs(a), a == defpath_py, a == sys.executable))
    a, d = run(script, "./env/bin/python", False, 24610)
    print("%-6s leg 2 (./env/bin/python):     argv[0] %s | absolute %s | == <job dir>/env/bin/python %s"
          % (name, a, os.path.isabs(a), a == os.path.join(d, "env", "bin", "python")))
shutil.rmtree(tmp)
