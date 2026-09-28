# r13 reviewer: the r12 repair records a cluster-hosted name *before* host_service is called. A backend whose
# host_service refuses before hosting anything (m70 dask: "refused naming the worker table") and whose
# release_service follows m70 ("awaited with timeout_s, a stop never acknowledged is the refusal").
# Leg "before" = plan text; leg "after" = record only once host_service returns (host_service owns its partial state).
import time

class ServiceUnavailable(Exception): pass

class Backend:
    def __init__(self): self.hosted, self.release_calls = {}, []
    def host_service(self, name):
        raise ServiceUnavailable(f"{name}: no worker's resources cover the recipe")  # nothing started
    def release_service(self, name, timeout_s=0.2):
        self.release_calls.append(name)
        if name not in self.hosted:
            time.sleep(timeout_s)  # no actor to acknowledge the stop
            raise RuntimeError(f"{name}: stop never acknowledged")

def start(backend, record_before):
    recorded = []
    def close():
        for n in recorded: backend.release_service(n)
    try:
        if record_before: recorded.append("svc")
        backend.host_service("svc")
        if not record_before: recorded.append("svc")
    except BaseException:
        close(); raise

def d6_exit(exc):  # m68a D6: service refusals are environment (1); anything else from the run is 3
    return 1 if isinstance(exc, ServiceUnavailable) else 3

for before in (True, False):
    b = Backend()
    t0 = time.monotonic()
    try: start(b, before)
    except Exception as e: out = e
    print(f"record_before={before} raised={type(out).__name__}({out}) exit={d6_exit(out)} "
          f"release_calls={b.release_calls} waited={time.monotonic() - t0:.2f}s")
