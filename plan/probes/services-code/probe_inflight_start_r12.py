# r12 reviewer: a managed spec whose own readiness poll times out. Leg A registers the child only once up
# ("services already up"); leg B registers it at Popen. Both run close() before re-raising.
import os, socket, subprocess, sys, time

class Unavailable(Exception): pass

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def up(port):
    try: socket.create_connection(("127.0.0.1", port), 0.1).close(); return True
    except OSError: return False

class Set:
    def __init__(self, register_at_popen): self.up, self.register_at_popen, self.last = [], register_at_popen, None
    def close(self):
        for p in self.up: p.terminate(); p.wait(5)
    def start(self, port, timeout_s=0.5):
        try:
            p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # never binds port
            self.last = p
            if self.register_at_popen: self.up.append(p)
            t0 = time.monotonic()
            while not up(port):
                if time.monotonic() - t0 > timeout_s: raise Unavailable("managed: check never passed")
                time.sleep(0.05)
            if not self.register_at_popen: self.up.append(p)
        except BaseException:
            self.close(); raise

for at_popen in (False, True):
    s = Set(at_popen)
    try: s.start(free_port())
    except Unavailable as e: raised = type(e).__name__
    s.last.poll()
    print(f"register_at_popen={at_popen} raised={raised} child_alive={s.last.returncode is None}")
    if s.last.returncode is None: s.last.terminate(); s.last.wait()
