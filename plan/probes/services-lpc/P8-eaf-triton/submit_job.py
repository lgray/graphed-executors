"""usage: SCHEDD=<name> submit_job.py <file.sub> [KEY=VALUE...]: spooled submit from the file's directory; prints ClusterId."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import htcondor2 as htc
from sched import choose
path = os.path.abspath(sys.argv[1]); os.chdir(os.path.dirname(path))
sub = htc.Submit(open(path).read())
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1); sub[k] = v
name, s = choose()
r = s.submit(sub, spool=True); s.spool(r)
print(f"SUBMITTED schedd={name} cluster={r.cluster()}", flush=True)
