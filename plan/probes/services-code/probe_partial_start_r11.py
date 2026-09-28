# r11 reviewer: a managed Popen started by an earlier spec, when a later spec raises and nothing tears it down,
# outlives the submitting interpreter (the attached, login-node case).
import os, signal, subprocess, sys, time
code = ("import subprocess, sys\n"
        "p = subprocess.Popen([sys.executable, '-m', 'http.server', '0'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "print(p.pid, flush=True)\n"
        "raise RuntimeError('ServiceUnavailable for the second spec')\n")
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
pid = int(r.stdout.split()[0])
time.sleep(0.5)
try:
    os.kill(pid, 0); alive = True
except ProcessLookupError:
    alive = False
print("parent rc", r.returncode, "| managed child", pid, "alive after parent exit:", alive)
if alive:
    os.kill(pid, signal.SIGTERM)
