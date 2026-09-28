"""Pick an LPC schedd the way the condor_submit wrapper / graphed _choose() does; SCHEDD env pins a name."""
import os, re, sys
import htcondor2 as htc
W = ("Name", "RecentDaemonCoreDutyCycle", "ShadowsRunning", "MaxJobsRunning", "TotalIdleJobs")
Q = 'FERMIHTC_DRAIN_LPCSCHEDD=?=FALSE && FERMIHTC_SCHEDD_TYPE=?="CMSLPC" && MaxJobsRunning!=0'
def wt(ad):
    return 0.7*ad["RecentDaemonCoreDutyCycle"]*100 + 0.2*ad["ShadowsRunning"]/ad["MaxJobsRunning"]*100 + 0.1*ad["TotalIdleJobs"]
def choose():
    for node in re.findall(r"[\w/:\-.]+", str(htc.param["FERMIHTC_REMOTE_POOL"])):
        c = htc.Collector(node)
        ads = c.query(htc.AdType.Schedd, Q, list(W))
        if ads:
            name = os.environ.get("SCHEDD") or str(min(ads, key=wt)["Name"])
            return name, htc.Schedd(c.locate(htc.DaemonType.Schedd, name))
    raise RuntimeError("no schedd")
if __name__ == "__main__":
    print(choose()[0])
