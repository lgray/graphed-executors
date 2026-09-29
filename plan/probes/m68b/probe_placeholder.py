"""m68b probe (local, POSIX sh): the placeholder `result.pkl` driver.sh writes before exec'ing the interpreter.

Run: python3 probe_placeholder.py > probe_placeholder.txt
The submit side pickles (False, RuntimeError(...)) and embeds its bytes as printf octal escapes in the script;
the script writes it and touches driver.log, then execs a "driver" that is (A) killed by SIGKILL before writing,
(B) writes its own result. Output: what result.pkl holds afterwards, loaded by pickle.
"""
import os
import pickle
import subprocess
import sys
import tempfile

blob = pickle.dumps((False, RuntimeError("the driver exited before writing a result; see driver.log")))
esc = "".join("\\%03o" % b for b in blob)
work = tempfile.mkdtemp(prefix="m68b-placeholder-")
for tag, body in (("A killed", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"),
                  ("B wrote", "import pickle; open('result.pkl', 'wb').write(pickle.dumps((True, 42)))")):
    open(os.path.join(work, "drv.py"), "w").write(body)
    script = os.path.join(work, "driver.sh")
    open(script, "w").write("#!/bin/sh\nprintf '%s' > result.pkl\n: >> driver.log\nexec %s drv.py\n" % (esc, sys.executable))
    os.chmod(script, 0o755)
    for f in ("result.pkl", "driver.log"):
        if os.path.exists(os.path.join(work, f)):
            os.remove(os.path.join(work, f))
    rc = subprocess.run([script], cwd=work).returncode
    ok, val = pickle.loads(open(os.path.join(work, "result.pkl"), "rb").read())
    print("%s: script rc %s, driver.log exists %s, result.pkl -> (%r, %s: %s)" % (
        tag, rc, os.path.exists(os.path.join(work, "driver.log")), ok, type(val).__name__, val))
print("blob bytes %d, script line length %d" % (len(blob), len(esc)))
