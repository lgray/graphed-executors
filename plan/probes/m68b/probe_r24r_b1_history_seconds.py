"""m68b r24-B1 review probe: B1 live row (a) asserts, for run 2's service cluster, `JobCurrentStartDate <= t <=
EnteredCurrentStatus` with `t = time.time()` taken at the task's GET. Condor stamps both attributes in whole seconds
(truncated), and the run's end removes the service (`_remove`: query + act) milliseconds after the last task, so t
and the removal can share a second. Q-04's probe (probe_r19_b1_history_times) walked only a 2.4 s gap.

Each trial: a running job; t = time.time(); sleep g; the `_remove` sequence (query, act Remove); then the history ad.
Printed per trial: g, frac(t), ECS - int(t), and the two predicates
  float: JobCurrentStartDate <= t <= EnteredCurrentStatus        (as the plan writes it)
  int:   JobCurrentStartDate <= t and int(t) <= EnteredCurrentStatus
g = 1.2 s is the control (a second boundary always lies between t and the removal).

Run: docker exec -u submituser r24r-mini /usr/bin/python3 /work/probe_r24r_b1_history_seconds.py
     (htcondor/mini:25.13.2-el9, container r24r-mini)
"""

import time

import htcondor2 as htc

schedd = htc.Schedd()
GAPS = [0.0, 0.0, 0.0, 0.0, 0.3, 0.3, 0.3, 1.2, 1.2]
clusters = []
for i, g in enumerate(GAPS):
    sub = htc.Submit({"universe": "vanilla", "executable": "/bin/sleep", "arguments": "600", "request_cpus": "1",
                      "request_memory": "64", "should_transfer_files": "YES", "transfer_output_files": '""',
                      "log": "/tmp/r24r-hs.log", "JobBatchName": "graphed-service-hs%d" % i})
    clusters.append(int(schedd.submit(sub).cluster()))
end = time.monotonic() + 180
while time.monotonic() < end:
    running = [c for c in clusters if (schedd.query("ClusterId == %d" % c, ["JobStatus"]) or [{}])[0].get("JobStatus") == 2]
    if len(running) == len(clusters):
        break
    time.sleep(1)
print("running:", len(running), "of", len(clusters))
time.sleep(1.5)  # every start stamped strictly before any t
ts = []
for c, g in zip(clusters, GAPS):
    t = time.time()
    time.sleep(g)
    schedd.query("ClusterId == %d" % c, ["JobStatus"])
    schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
    ts.append(t)
    time.sleep(0.37)  # spread t over different fractions of a second
time.sleep(3)
fails = {"float": 0, "int": 0}
for c, g, t in zip(clusters, GAPS, ts):
    h = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "JobCurrentStartDate", "EnteredCurrentStatus"], match=1))[0]
    s, e = h["JobCurrentStartDate"], h["EnteredCurrentStatus"]
    pf, pi = s <= t <= e, s <= t and int(t) <= e
    print("g=%.1f frac(t)=%.2f ECS-int(t)=%d JobStatus=%s float:%s int:%s" % (g, t % 1, e - int(t), h["JobStatus"], pf, pi))
    if g < 1:
        fails["float"] += not pf
        fails["int"] += not pi
print("trials with g < 1 s failing: float %d, int %d of %d" % (fails["float"], fails["int"], sum(g < 1 for g in GAPS)))
