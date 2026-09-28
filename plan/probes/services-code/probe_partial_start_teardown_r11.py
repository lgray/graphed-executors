# r11 planner: start() that closes what it started before re-raising leaves no child and a free port;
# the same start without the teardown leaves the child alive (control leg).
import os, signal, socket, subprocess, sys, time

class Unavailable(Exception): pass

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def up(port):
    try:
        socket.create_connection(("127.0.0.1", port), 0.2).close(); return True
    except OSError:
        return False

class Set:
    def __init__(self, teardown): self.procs, self.teardown = [], teardown
    def close(self):
        for p in self.procs:
            p.terminate(); p.wait(5)
    def start(self, port):
        try:
            p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.procs.append(p)
            while not up(port): time.sleep(0.05)
            raise Unavailable("second spec: no launch, no endpoint")
        except BaseException:
            if self.teardown: self.close()
            raise

def alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False

def port_free(port):
    s = socket.socket()
    try: s.bind(("127.0.0.1", port)); return True
    except OSError: return False
    finally: s.close()

for teardown in (True, False):
    port, s = free_port(), None
    s = Set(teardown)
    try: s.start(port)
    except Unavailable as e: raised = type(e).__name__
    pid = s.procs[0].pid
    # reap only; a zombie would still answer os.kill(pid, 0)
    s.procs[0].poll()
    print(f"teardown={teardown} raised={raised} pid_alive={alive(pid) and s.procs[0].returncode is None} port_free={port_free(port)}")
    if s.procs[0].returncode is None: s.procs[0].terminate(); s.procs[0].wait()
