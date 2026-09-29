"""r17-B2: does `RETRY driver 2 UNLESS-EXIT 3` retry a driver node that dies by SIGKILL (or exec failure 127)
after writing placeholder result.pkl/driver.log? DAG as B2 submits it (UseDagDir + AddToEnv strict 0), SERVICE running.
Run (htcondor/mini 25.13.2, NUM_CPUS=8): docker exec -u submituser -w /home/submituser <c> python3 probe_r17_b2_sigretry.py"""
import os, time, htcondor2 as htc
HOME = os.path.expanduser("~"); os.chdir(HOME)
schedd = htc.Schedd()
DRV = """#!/bin/sh
printf 'placeholder' > result.pkl
echo "driver.sh start" >> driver.log
sleep 3
case "$1" in k) kill -9 $$ ;; x) exec /nonexistent/python -m x ;; esac
exit 0
"""
def dag(tag, mode):
    d = os.path.join(HOME, "r17b2-" + tag + "-" + str(int(time.time()))); os.makedirs(d)
    open(os.path.join(d, "driver.sh"), "w").write(DRV); os.chmod(os.path.join(d, "driver.sh"), 0o755)
    open(os.path.join(d, "driver.sub"), "w").write(
        "universe=vanilla\nexecutable=%s/driver.sh\narguments=%s\nshould_transfer_files=YES\n"
        "when_to_transfer_output=ON_EXIT_OR_EVICT\ntransfer_output_files=result.pkl,driver.log\n"
        "output=driver.out\nerror=driver.err\nlog=driver.condor.log\nrequest_memory=64\ninitialdir=%s\nqueue\n" % (d, mode, d))
    open(os.path.join(d, "svc0.sub"), "w").write(
        "universe=vanilla\nexecutable=/bin/sleep\narguments=3600\nrequest_memory=64\nlog=svc.log\nperiodic_remove = JobStatus == 5\nqueue\n")
    open(os.path.join(d, "run.dag"), "w").write("JOB driver driver.sub\nSERVICE svc0 svc0.sub\nRETRY driver 2 UNLESS-EXIT 3\n")
    r = schedd.submit(htc.Submit.from_dag(os.path.join(d, "run.dag"), {"UseDagDir": True, "AddToEnv": "_CONDOR_DAGMAN_USE_STRICT=0"}))
    return d, r.cluster()
runs = {t: dag(t, m) for t, m in (("sigkill", "k"), ("execfail", "x"))}
for t, (d, c) in runs.items():
    t0 = time.time()
    while schedd.query("ClusterId == %d" % c, ["JobStatus"]) and time.time() - t0 < 400:
        held = schedd.query("DAGManJobId == %d && DAGNodeName == \"driver\"" % c, ["ClusterId", "JobStatus", "HoldReasonCode"])
        if any(a.get("JobStatus") == 5 for a in held): print(t, "driver node HELD", [dict(a) for a in held]); break
        time.sleep(3)
    dm = list(schedd.history("ClusterId == %d" % c, ["JobStatus", "ExitCode"], match=1))
    print(t, "DAGMan", [dict(a) for a in dm], "after %.0fs" % (time.time() - t0))
    for a in schedd.history("DAGManJobId == %d" % c, ["ClusterId", "DAGNodeName", "JobStatus", "ExitCode", "ExitBySignal", "ExitSignal", "HoldReasonCode"]):
        print(t, "  node", dict(a))
    print(t, "  result.pkl:", open(os.path.join(d, "result.pkl")).read() if os.path.exists(os.path.join(d, "result.pkl")) else None)
    print(t, "  dagman.out retry lines:", [l.strip() for l in open(os.path.join(d, "run.dag.dagman.out")) if "retry" in l.lower() or "RETRY" in l][:8])
