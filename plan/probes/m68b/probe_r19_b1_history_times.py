# r19-B1: what B1's live witness reads from history for a removed running job: JobBatchName, JobCurrentStartDate,
# EnteredCurrentStatus (JobStatus 3), and a time t taken inside the job while it ran. Run as submituser on htcondor/mini.
import os, time, htcondor2 as htc
H = os.path.expanduser("~"); s = htc.Schedd()
j = H + "/r19hist"; os.makedirs(j, exist_ok=True)
open(j + "/run.sh", "w").write("#!/bin/sh\nsleep 5; python3 -c 'import time; print(time.time())' > %s/t.txt\nsleep 600\n" % j)
os.chmod(j + "/run.sh", 0o755)
r = s.submit(htc.Submit({"executable": j + "/run.sh", "initialdir": j, "should_transfer_files": "YES",
                         "when_to_transfer_output": "ON_EXIT", "output": "o", "error": "e", "log": "l",
                         "request_memory": "64", "JobBatchName": "graphed-service-nonce1-0123456789abcdef",
                         "job_max_vacate_time": "30"}))
c = r.cluster()
while not os.path.exists(j + "/t.txt") or not open(j + "/t.txt").read().strip():
    time.sleep(1)
t = float(open(j + "/t.txt").read())
time.sleep(2)
s.act(htc.JobAction.Remove, "ClusterId==%d" % c)
t_rm = time.time()
while s.query("ClusterId==%d" % c, ["JobStatus"]):
    time.sleep(1)
print("left the queue %.1fs after act(Remove)" % (time.time() - t_rm))
h = list(s.history("ClusterId==%d" % c, ["JobBatchName", "JobStatus", "JobCurrentStartDate", "EnteredCurrentStatus"], match=1))
ad = dict(h[0]); ad.pop("ServerTime", None)
print("history", ad)
print("t (in job) = %.1f" % t)
print("JobCurrentStartDate <= t <= EnteredCurrentStatus:", ad["JobCurrentStartDate"] <= t <= ad["EnteredCurrentStatus"])
print("EnteredCurrentStatus - int(t_rm) =", ad["EnteredCurrentStatus"] - int(t_rm))
