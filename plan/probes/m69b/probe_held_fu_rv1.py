"""The new recorder row's scenario at 5fdb3c0, printing the refusal and the schedd actions on the pilots' cluster:
the same call that names the pilots "held until it closes" condor-holds their idle jobs, and releases them on refusal."""

import sys

sys.path.insert(0, "/work/tests/extra/m69b")
import pytest  # noqa: E402
import test_m69b_schedulable as t  # noqa: E402


def test_probe(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    pool = t.SlotPool(pytest.importorskip("classad2"))
    monkeypatch.setattr(t.launch, "_htcondor", lambda: pool)
    monkeypatch.setattr(t.launch, "CLOSE_WAIT_S", 0.0)
    pilots = t.CondorPilots("generic", log_dir=tmp_path, request_memory_mb=500)
    backend = t.HTCondorBackend(pilots, 1, host="127.0.0.1", service_hosts=("cluster",))
    try:
        backend._need()
        pool.running.add(pilots.cluster[1])
        with pytest.raises(t.ServiceUnavailable) as refused:
            t.ServiceSet([t.spec("web", 600)], backend, scope="later").start()
        print("\nPILOTS CLUSTER:", pilots.cluster[1])
        print("MESSAGE:", refused.value.legs["managed"])
        for entry in pool.log:
            if entry[0] == "act":
                print("SCHEDD ACT:", entry)
    finally:
        backend.close()
