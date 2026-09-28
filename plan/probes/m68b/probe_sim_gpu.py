"""m68b pool probe: a simulated GPU on minicondor, the CI config a GPU recipe needs to match.

Run (root installs the config, then the probe as the submitter):
  docker exec m68b-probe-pool sh -c 'cp /probes/sim_gpu.config /etc/condor/config.d/99-m68b-gpu && condor_restart -daemon startd'
  docker exec -u submituser m68b-probe-pool python3 /probes/probe_sim_gpu.py > probe_sim_gpu.txt
 G1 request_gpus=1 runs, and the job sees its assigned device; G2 request_gpus=2 never matches (idle).
"""
import os
import time

import htcondor2 as htc

print(open("/etc/condor/config.d/99-m68b-gpu").read().strip())
time.sleep(15)
print("slot TotalGPUs:", [a.get("TotalGPUs") for a in htc.Collector().query(htc.AdType.Startd, projection=["TotalGPUs"])])
schedd = htc.Schedd()
os.makedirs(os.path.expanduser("~/m68b-gpu"), exist_ok=True)
os.chdir(os.path.expanduser("~/m68b-gpu"))
base = {"universe": "vanilla", "executable": "/usr/bin/env", "request_memory": "64", "should_transfer_files": "YES",
        "transfer_output_files": '""', "log": "gpu.log"}
c1 = schedd.submit(htc.Submit({**base, 
                               "request_gpus": "1", "output": "g1.out"})).cluster()
c2 = schedd.submit(htc.Submit({**base, "request_gpus": "2", "output": "g2.out"})).cluster()
end = time.monotonic() + 90
while time.monotonic() < end and schedd.query("ClusterId == %d" % c1, ["JobStatus"]):
    time.sleep(2)
h = list(schedd.history("ClusterId == %d" % c1, ["JobStatus", "ExitCode", "AssignedGPUs"], match=1))[0]
print("G1 request_gpus=1:", {k: h.get(k) for k in ("JobStatus", "ExitCode", "AssignedGPUs")}, [l for l in open("g1.out").read().split() if "VISIBLE" in l or "GPU" in l])
print("G2 request_gpus=2 after G1 finished:", schedd.query("ClusterId == %d" % c2, ["JobStatus", "NumJobStarts"])[0])
schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c2, reason="probe done")
