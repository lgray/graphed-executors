"""m70 premise: dask can pin a long-lived task to one worker (workers=, allow_other_workers=False) that
announces to the driver's HTTP route while another task keeps running on the other worker."""
import http.server, json, os, sys, threading, time, urllib.request
from dask.distributed import Client, LocalCluster

hits = []
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        hits.append((self.path, self.rfile.read(int(self.headers["Content-Length"])).decode())); self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def service(url, name, hold_s):
    import os, socket, time, urllib.request
    from distributed import get_worker
    w = get_worker()
    body = json.dumps({"name": name, "pid": os.getpid(), "worker": w.address}).encode()
    urllib.request.urlopen(urllib.request.Request(url + "/announce", data=body, method="POST"), timeout=5)
    time.sleep(hold_s)
    return w.address

def other(_):
    import os
    from distributed import get_worker
    return get_worker().address, os.getpid()

def service_var(name, hold_s):
    """M3 leg: announce + stop over scheduler-mediated distributed.Variable, no driver listener."""
    import os, time
    from distributed import Variable, get_worker
    w = get_worker()
    Variable(f"svc-{name}").set({"name": name, "pid": os.getpid(), "worker": w.address})
    stop = Variable(f"stop-{name}")
    t0 = time.time()
    while time.time() - t0 < hold_s:
        try:
            if stop.get(timeout=0.2):
                return ("stopped", w.address)
        except Exception:
            pass
    return ("timeout", w.address)


def probe_variable():
    import sys
    from distributed import Variable
    with LocalCluster(n_workers=2, threads_per_worker=1, processes=True, dashboard_address=None) as cluster, Client(cluster) as c:
        workers = sorted(c.scheduler_info()["workers"])
        t0 = time.time()
        svc = c.submit(service_var, "svc", 20.0, workers=[workers[0]], allow_other_workers=False, key="svc-var", pure=False)
        ann = Variable("svc-svc").get(timeout=10)
        print("VARIABLE_ANNOUNCE_FROM_PINNED_WORKER", ann["worker"] == workers[0], ann, f"after {time.time()-t0:.1f}s, no driver listener")
        others = c.gather([c.submit(other, i, pure=False) for i in range(4)])
        print("OTHER_TASKS_RAN_ELSEWHERE_WHILE_VARIABLE_SERVICE_HELD", all(a == workers[1] for a, _ in others), sorted({a for a, _ in others}), "svc done?", svc.done())
        t1 = time.time()
        Variable("stop-svc").set(True)
        res = svc.result(timeout=10)
        print("STOP_VIA_VARIABLE", res[0] == "stopped", res, f"after {time.time()-t1:.1f}s")


def service_event(name, hold_s):
    """E1 leg: stop via distributed.Event.wait(timeout) (a bool per miss, no scheduler ERROR)."""
    import os, time
    from distributed import Event, Variable, get_worker
    w = get_worker()
    Variable(f"svc-{name}").set({"name": name, "pid": os.getpid(), "worker": w.address})
    stop = Event(f"stop-{name}")
    t0 = time.time()
    while time.time() - t0 < hold_s:
        if stop.wait(timeout=0.5):
            return ("stopped", w.address)
    return ("timeout", w.address)


def probe_event():
    from distributed import Event, Variable
    with LocalCluster(n_workers=2, threads_per_worker=1, processes=True, dashboard_address=None) as cluster, Client(cluster) as c:
        workers = sorted(c.scheduler_info()["workers"])
        svc = c.submit(service_event, "ev", 20.0, workers=[workers[0]], allow_other_workers=False, key="svc-ev", pure=False)
        ann = Variable("svc-ev").get(timeout=10)
        others = c.gather([c.submit(other, i, pure=False) for i in range(4)])
        t1 = time.time()
        Event("stop-ev").set()
        res = svc.result(timeout=10)
        print("STOP_VIA_EVENT", res[0] == "stopped" and ann["worker"] == workers[0] and all(a == workers[1] for a, _ in others), res, f"after {time.time()-t1:.2f}s; announce from pinned worker, 4 tasks ran elsewhere meanwhile")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "event":
    probe_event()
    raise SystemExit(0)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "variable":
    probe_variable()
    raise SystemExit(0)

if __name__ == "__main__":
    with LocalCluster(n_workers=2, threads_per_worker=1, processes=True, dashboard_address=None) as cluster, Client(cluster) as c:
        workers = sorted(c.scheduler_info()["workers"])
        t0 = time.time()
        svc = c.submit(service, f"http://127.0.0.1:{port}", "svc", 6.0, workers=[workers[0]], allow_other_workers=False, key="svc", pure=False)
        for _ in range(50):
            if hits: break
            time.sleep(0.1)
        ann = json.loads(hits[0][1]) if hits else None
        print("ANNOUNCE_FROM_PINNED_WORKER", ann is not None and ann["worker"] == workers[0], ann, f"after {time.time()-t0:.1f}s")
        others = c.gather([c.submit(other, i, pure=False) for i in range(4)])
        print("OTHER_TASKS_RAN_ELSEWHERE_WHILE_SERVICE_HELD", all(a == workers[1] for a, _ in others), sorted({a for a, _ in others}), "svc done?", svc.done())
        who = c.who_has(svc) if svc.done() else None
        svc.cancel()
        time.sleep(0.5)
        print("CANCEL_RUNNING", svc.cancelled() or svc.status, "| processing after cancel:", {k: len(v) for k, v in c.processing().items()})
    srv.shutdown()
