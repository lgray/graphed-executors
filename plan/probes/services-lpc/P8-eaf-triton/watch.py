"""usage: SCHEDD=<name> watch.py <cluster> <timeout_s> [retrieve 0|1]: prints state changes of the cluster and its DAG nodes."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import htcondor2 as htc
from sched import choose
c, tmo = int(sys.argv[1]), float(sys.argv[2]); ret = len(sys.argv) > 3 and sys.argv[3] == "1"
name, s = choose()
con = f"ClusterId == {c} || DAGManJobId == {c}"
P = ["ClusterId", "ProcId", "JobStatus", "DAGNodeName", "JobUniverse", "HoldReason", "HoldReasonCode", "RemoveReason", "RemoteHost", "ExitCode", "LastRemoteHost", "JobCurrentStartDate", "CompletionDate"]
seen, t0 = {}, time.time()
def stamp(): return time.strftime("%H:%M:%SZ", time.gmtime())
while time.time() - t0 < tmo:
    ads = s.query(constraint=con, projection=P)
    for ad in ads:
        k = (ad["ClusterId"], ad.get("ProcId"))
        v = tuple(str(ad.get(p)) for p in P[2:])
        if seen.get(k) != v:
            seen[k] = v
            print(stamp(), k, dict(zip(P[2:], v)), flush=True)
    dag = [a for a in ads if a["ClusterId"] == c]
    if not dag or dag[0].get("JobStatus") in (3, 4) and not ret:
        break
    if ret and dag and dag[0].get("JobStatus") == 4:
        print(stamp(), "retrieve", s.retrieve(f"ClusterId == {c}"), flush=True); break
    time.sleep(15)
print(stamp(), f"elapsed={time.time()-t0:.0f}s", flush=True)
for ad in s.history(con, P, match=50):
    print("HIST", {p: ad.get(p) for p in P})
