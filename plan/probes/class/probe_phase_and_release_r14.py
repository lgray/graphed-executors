"""r14 planner premises on exec-main (m67):
A. driver.main classifies by phase before runner.run (any type -> 1) and by type inside it (OSError -> 3).
B. HTCondorBackend.close: a raising launcher.stop skips server.shutdown (port held); control: port freed.
"""
import os, pickle, socket, sys, tempfile, json
from pathlib import Path
from graphed_executors.htcondor_backend import driver
from graphed_executors.htcondor_backend.backend import HTCondorBackend


class FakeRunner:
    def __init__(self, where):
        self.where = where
    def wait_for_pilots(self):
        if self.where == "before":
            raise OSError("port range held")
        return 1
    def run(self, plan):
        raise OSError("plan task OSError")
    def close(self):
        pass


def phase(where):
    job = Path(tempfile.mkdtemp())
    (job / "run.json").write_text(json.dumps({}))
    (job / "plan.pkl").write_bytes(pickle.dumps(None))
    driver._runner = lambda run, job, log: FakeRunner(where)
    code = driver.main([str(job)])
    ok, payload = pickle.loads((job / "result.pkl").read_bytes())
    return code, type(payload).__name__


print("A before runner.run:", phase("before"))
print("A inside runner.run:", phase("inside"))


class Launcher:
    def __init__(self, raise_stop):
        self.raise_stop = raise_stop
    def start(self, url, secret, n):
        pass
    def stop(self):
        if self.raise_stop:
            raise RuntimeError("schedd query failed")


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


for raise_stop in (False, True):
    b = HTCondorBackend(Launcher(raise_stop), 1, host="127.0.0.1", port_range=(0, 0))
    port = int(b._server.url.rsplit(":", 1)[1].split("/")[0])
    try:
        b.close()
        err = None
    except Exception as exc:
        err = type(exc).__name__
    free = port_free(port)
    print(f"B raise_stop={raise_stop}: close raised {err}, port freed {free}")
    if not free:
        b._server.shutdown()
