"""r6 M8/M9 premises: (M8) a parsl HTEX hosted actor that polls its service before announcing gives a
first-task GET that succeeds, while announcing at once races the bind; (M9) on a single-machine dask
LocalCluster every worker's host identity (Machine from $_CONDOR_MACHINE_AD, else getfqdn) equals the driver's."""
import sys, tempfile, time, uuid
from graphed_executors.parsl_backend.transport_peer import _open_driver_endpoint
from graphed_executors.parsl_backend.launch import start_htex, stop_htex
from probe_ready_tasks import service_main, get, identity


def parsl_leg(wait, trials):
    ex = start_htex(workers=2, run_dir=tempfile.mkdtemp(prefix="parsl-ready-"))
    firsts = []
    try:
        for _ in range(trials):
            nonce = uuid.uuid4().hex
            drv = _open_driver_endpoint(nonce)
            svc = ex.submit(service_main, {}, {"epoch": nonce, "driver_host": drv.host, "driver_port": drv.port, "wait": wait})
            got = None; t0 = time.monotonic()
            while got is None and time.monotonic() - t0 < 30:
                got = drv.recv(timeout=0.05)
            if got is None:
                print('NO_ANNOUNCE', svc.done() and svc.exception()); raise SystemExit(1)
            _, (_, _, host, port, _, _, polls) = got
            first = ex.submit(get, {}, f"http://{host}:{port}/").result(timeout=30)
            firsts.append((first, polls))
            drv.close()
            svc.result(timeout=30)  # the actor ends itself after 1.5 s
    finally:
        stop_htex(ex)
    return firsts


if __name__ == "__main__":
    for wait in (False, True):
        r = parsl_leg(wait, 5)
        ok = sum(1 for f, _ in r if f == 200)
        print(f"PARSL wait_before_announce={wait}: first-task GET 200 in {ok}/{len(r)}; (status, polls)={r}")
    from distributed import Client, LocalCluster
    with LocalCluster(n_workers=2, processes=True, threads_per_worker=1) as lc, Client(lc) as c:
        w = c.run(identity)
        print("DASK driver identity", identity(), "workers", sorted(set(w.values())), "all equal:", set(w.values()) == {identity()})
