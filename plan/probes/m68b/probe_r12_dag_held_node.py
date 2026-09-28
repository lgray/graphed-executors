# Run: docker exec -u submituser <htcondor/mini container> python3 /probes/probe_r12_dag_held_node.py (run 1 of the transcript used the same script without driver.sh, so the executable was missing)
"""r12-B2: a reused DAG log_dir holding a previous run's result.pkl; the new DAG's driver node is killed by a
signal on each start (as an OOM kill would), so it never writes result.pkl. What does DAGMan report, and what is left in the dir?"""
import os, pickle, shutil, time
import htcondor2 as htc

schedd = htc.Schedd()
d = os.path.expanduser("~/r12b2-stale-kill")
shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
open(os.path.join(d, "driver.sh"), "w").write("#!/bin/sh\nkill -9 $$\n"); os.chmod(os.path.join(d, "driver.sh"), 0o755)
open(os.path.join(d, "result.pkl"), "wb").write(pickle.dumps((True, "PREVIOUS RUN'S VALUE")))
open(os.path.join(d, "driver.sub"), "w").write(
    "universe = vanilla\nexecutable = %s/driver.sh\ninitialdir = %s\nshould_transfer_files = YES\n"
    "transfer_output_files = result.pkl\nlog = driver.condor.log\nrequest_memory = 64\nqueue\n" % (d, d))
open(os.path.join(d, "svc0.sub"), "w").write(
    "universe = vanilla\nexecutable = /bin/sleep\narguments = 600\nshould_transfer_files = YES\n"
    "transfer_output_files = \"\"\nrequest_memory = 64\nlog = svc0.log\nqueue\n")
open(os.path.join(d, "run.dag"), "w").write(
    "JOB driver driver.sub\nSERVICE svc0 svc0.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
os.chdir(os.path.expanduser("~"))
c = schedd.submit(htc.Submit.from_dag(os.path.join(d, "run.dag"), {"usedagdir": True, "force": True})).cluster()
t0 = time.monotonic()
while schedd.query("ClusterId == %d || DAGManJobId == %d" % (c, c), ["ClusterId"]) and time.monotonic() - t0 < 400:
    time.sleep(3)
h = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "ExitCode"], match=1))
print("DAGMan", c, "history:", [dict(JobStatus=a.get("JobStatus"), ExitCode=a.get("ExitCode")) for a in h],
      "after %.0fs" % (time.monotonic() - t0))
nodes = list(schedd.history("DAGManJobId == %d" % c, ["DAGNodeName", "JobStatus", "ExitCode", "RemoveReason"], match=10))
print("node history:", [dict(n=a.get("DAGNodeName"), s=a.get("JobStatus"), rr=a.get("RemoveReason")) for a in nodes])
print("result.pkl now holds:", pickle.loads(open(os.path.join(d, "result.pkl"), "rb").read()))
out = open(os.path.join(d, "run.dag.dagman.out")).read().splitlines()
print("dagman.out tail:"); [print("  ", l) for l in out if "ERROR" in l or "failed" in l.lower() or "submit" in l.lower()][-12:]
