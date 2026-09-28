"""r16-B2: a reused DAG log_dir holding a previous run's result.pkl; the new DAG's driver node is REMOVED
on each start (periodic_remove after 5 s running, as a site's wall-time SYSTEM_PERIODIC_REMOVE or a
user condor_rm of the node would). What does DAGMan report (RunHandle(dag=True) maps ExitCode 1 -> failed),
and what does result.pkl hold?"""
import os, pickle, shutil, time
import htcondor2 as htc

schedd = htc.Schedd()
d = os.path.expanduser("~/r16b2-removed")
shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
open(os.path.join(d, "driver.sh"), "w").write("#!/bin/sh\nsleep 300\n"); os.chmod(os.path.join(d, "driver.sh"), 0o755)
open(os.path.join(d, "result.pkl"), "wb").write(pickle.dumps((True, "PREVIOUS RUN'S VALUE")))
open(os.path.join(d, "driver.sub"), "w").write(
    "universe = vanilla\nexecutable = %s/driver.sh\ninitialdir = %s\nshould_transfer_files = YES\n"
    "when_to_transfer_output = ON_EXIT_OR_EVICT\n"
    "transfer_output_files = result.pkl\nlog = driver.condor.log\nrequest_memory = 64\n"
    "periodic_remove = JobStatus == 2 && (time() - EnteredCurrentStatus) > 5\nqueue\n" % (d, d))
open(os.path.join(d, "svc0.sub"), "w").write(
    "universe = vanilla\nexecutable = /bin/sleep\narguments = 600\nshould_transfer_files = YES\n"
    "transfer_output_files = \"\"\nrequest_memory = 64\nlog = svc0.log\nperiodic_remove = JobStatus == 5\nqueue\n")
open(os.path.join(d, "run.dag"), "w").write(
    "JOB driver driver.sub\nSERVICE svc0 svc0.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
os.chdir(os.path.expanduser("~"))
c = schedd.submit(htc.Submit.from_dag(os.path.join(d, "run.dag"), {"usedagdir": True, "force": True})).cluster()
t0 = time.monotonic()
while schedd.query("ClusterId == %d || DAGManJobId == %d" % (c, c), ["ClusterId"]) and time.monotonic() - t0 < 500:
    time.sleep(3)
h = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "ExitCode", "JobUniverse"], match=1))
print("DAGMan", c, "history:", [dict(JobStatus=a.get("JobStatus"), ExitCode=a.get("ExitCode"), JobUniverse=a.get("JobUniverse")) for a in h],
      "after %.0fs" % (time.monotonic() - t0))
nodes = list(schedd.history("DAGManJobId == %d" % c, ["DAGNodeName", "JobStatus", "ExitCode", "RemoveReason"], match=10))
print("node history:", [dict(n=a.get("DAGNodeName"), s=a.get("JobStatus"), x=a.get("ExitCode"), rr=a.get("RemoveReason")) for a in nodes])
print("result.pkl now holds:", pickle.loads(open(os.path.join(d, "result.pkl"), "rb").read()))
print("files:", sorted(os.listdir(d)))
