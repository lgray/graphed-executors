"""m68b r25-B1 review probe: the fail direction of the live row's history bounds after the M41 fold.

run 2: JobCurrentStartDate <= t and int(t) <= EnteredCurrentStatus   (int form, the fold)
       JobCurrentStartDate <= t <= EnteredCurrentStatus              (float form, pre-fold)
run 1: EnteredCurrentStatus < t                                      (removed before t, unchanged)
Each case is one job whose start/removal is placed against t as the named implementation would place it.

Run: docker exec -u submituser r25r-mini /usr/bin/python3 /work/probe_r25r_b1_history_mutants.py
     (htcondor/mini:25.13.2-el9, container r25r-mini)
"""

import time

import htcondor2 as htc

schedd = htc.Schedd()


def submit(name):
    sub = htc.Submit({"universe": "vanilla", "executable": "/bin/sleep", "arguments": "600", "request_cpus": "1",
                      "request_memory": "64", "should_transfer_files": "YES", "transfer_output_files": '""',
                      "log": "/tmp/r25r-hm.log", "JobBatchName": "graphed-service-" + name})
    return int(schedd.submit(sub).cluster())


def wait_running(c):
    end = time.monotonic() + 120
    while time.monotonic() < end:
        if (schedd.query("ClusterId == %d" % c, ["JobStatus"]) or [{}])[0].get("JobStatus") == 2:
            return
        time.sleep(0.2)
    raise SystemExit("cluster %d never ran" % c)


def remove(c):
    schedd.query("ClusterId == %d" % c, ["JobStatus"])
    schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)


def early_in_second():
    while time.time() % 1 > 0.1:
        time.sleep(0.01)


cases = {}
# correct: running before t, removed milliseconds after t (run 2's end)
c = submit("correct"); wait_running(c); time.sleep(1.5); early_in_second()
t = time.time(); remove(c); cases["correct (removed ms after t)"] = (c, t)
# mutant: run 2's service starts only after t
t = time.time(); c = submit("late"); wait_running(c); time.sleep(1.5); remove(c)
cases["mutant: started after t"] = (c, t)
# mutant: run 2's service removed before t, a second boundary between
c = submit("early1"); wait_running(c); time.sleep(1.5); remove(c); time.sleep(1.2)
cases["mutant: removed >=1 s before t"] = (c, time.time())
# mutant: run 2's service removed before t, same second
c = submit("early0"); wait_running(c); time.sleep(1.5); early_in_second(); remove(c)
cases["mutant: removed before t, same second"] = (c, time.time())
# mutant: service kept past its run's end (leaked, removed later)
c = submit("leak"); wait_running(c); time.sleep(1.5); t = time.time(); time.sleep(2.5); remove(c)
cases["mutant: leaked (removed 2.5 s after t)"] = (c, t)
time.sleep(3)
for label, (c, t) in cases.items():
    h = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "JobCurrentStartDate", "EnteredCurrentStatus"], match=1))[0]
    s, e = h["JobCurrentStartDate"], h["EnteredCurrentStatus"]
    print("%-40s frac(t)=%.2f S-int(t)=%+d E-int(t)=%+d JobStatus=%s | run2 int:%s float:%s | run1 E<t:%s"
          % (label, t % 1, s - int(t), e - int(t), h["JobStatus"], s <= t and int(t) <= e, s <= t <= e, e < t))
