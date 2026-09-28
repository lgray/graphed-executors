# Run: docker exec -u submituser <htcondor/mini container> python3 /probes/probe_r13_held_service_node.py
"""r13-B2 variant: svc0.sub also carries periodic_remove = JobStatus == 5.
 a DAG whose SERVICE node is held at input transfer while its driver node runs 200 s and exits 0.
(1) does the DAGMan ad read DAG_JobsHeld > 0 (plan: status 'held') while the DAG is still going to succeed?
(2) does a query projected on m67's STATUS_ATTRS alone carry DAG_JobsHeld?"""
import os, time
import htcondor2 as htc

schedd = htc.Schedd()
d = os.path.expanduser("~/r13b2-held-svc-prm")
os.system("rm -rf " + d); os.makedirs(d)
open(os.path.join(d, "driver.sh"), "w").write("#!/bin/sh\nsleep 200\necho ok > result.pkl\n"); os.chmod(os.path.join(d, "driver.sh"), 0o755)
open(os.path.join(d, "driver.sub"), "w").write(
    "universe = vanilla\nexecutable = %s/driver.sh\ninitialdir = %s\nshould_transfer_files = YES\n"
    "transfer_output_files = result.pkl\nlog = driver.condor.log\nrequest_memory = 64\nqueue\n" % (d, d))
open(os.path.join(d, "svc0.sub"), "w").write(
    "universe = vanilla\nexecutable = /bin/sleep\narguments = 600\nshould_transfer_files = YES\n"
    "transfer_input_files = %s/no-such-models\ntransfer_output_files = \"\"\nperiodic_remove = JobStatus == 5\nrequest_memory = 64\nlog = svc0.log\nqueue\n" % d)
open(os.path.join(d, "run.dag"), "w").write("JOB driver driver.sub\nSERVICE svc0 svc0.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
os.chdir(os.path.expanduser("~"))
c = schedd.submit(htc.Submit.from_dag(os.path.join(d, "run.dag"), {"usedagdir": True, "force": True})).cluster()
t0 = time.monotonic(); last = None
while time.monotonic() - t0 < 600:
    full = list(schedd.query("ClusterId == %d" % c, ["JobStatus", "HoldReasonCode", "ExitCode", "DAG_JobsHeld"]))
    if not full:
        break
    m67 = list(schedd.query("ClusterId == %d" % c, ["JobStatus", "HoldReasonCode", "ExitCode"]))
    row = (full[0].get("JobStatus"), full[0].get("DAG_JobsHeld"), "DAG_JobsHeld" in m67[0])
    if row != last:
        print("t=%3.0fs DAGMan JobStatus=%s DAG_JobsHeld=%s | in m67-projected ad: %s" % ((time.monotonic() - t0,) + row), flush=True)
        last = row
    time.sleep(3)
h = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "ExitCode"], match=1))
print("t=%3.0fs DAGMan history:" % (time.monotonic() - t0), [dict(JobStatus=a.get("JobStatus"), ExitCode=a.get("ExitCode")) for a in h])
nodes = list(schedd.history("DAGManJobId == %d" % c, ["DAGNodeName", "JobStatus", "ExitCode", "HoldReasonCode", "RemoveReason"], match=10))
print("node history:", [dict(n=a.get("DAGNodeName"), s=a.get("JobStatus"), x=a.get("ExitCode"), rr=a.get("RemoveReason")) for a in nodes])
