import os, time, htcondor2 as htc
H=os.path.expanduser("~"); b=os.path.join(H,"r17"); os.makedirs(b+"/src/models/m",exist_ok=True); os.makedirs(b+"/job/service/models/m",exist_ok=True)
open(b+"/src/serve.sh","w").write("#!/bin/sh\necho SERVE ran in $(pwd)\n"); os.chmod(b+"/src/serve.sh",0o755)
open(b+"/src/models/m/cfg","w").write("x")
os.makedirs(b+"/src/models/empty",exist_ok=True); os.makedirs(b+"/job/service/models/empty",exist_ok=True)
for s,d in (("serve.sh","serve.sh"),("models/m/cfg","models/m/cfg")):
    p=b+"/job/service/"+d
    if not os.path.lexists(p): os.symlink(b+"/src/"+s,p)
open(b+"/job/look.sh","w").write("#!/bin/sh\nls -la service service/models; cd service && ./serve.sh; echo rc=$?\n"); os.chmod(b+"/job/look.sh",0o755)
s=htc.Schedd()
for spool in (False, True):
  r=s.submit(htc.Submit({"executable":b+"/job/look.sh","initialdir":b+"/job","transfer_input_files":b+"/job/service","should_transfer_files":"YES","when_to_transfer_output":"ON_EXIT","output":"o%d"%spool,"error":"e%d"%spool,"log":"l","request_memory":"64"}),spool=spool)
  c=r.cluster()
  if spool: s.spool(r)
  for _ in range(60):
    q=s.query("ClusterId==%d"%c,["JobStatus","HoldReason"])
    if not q or q[0]["JobStatus"]==4: break
    if q[0]["JobStatus"]==5 and "pool" not in str(q[0].get("HoldReason")): print("held",q[0]["HoldReason"]); break
    time.sleep(2)
  if spool: s.retrieve("ClusterId==%d"%c); s.act(htc.JobAction.Remove,"ClusterId==%d"%c)
  print("spool",spool); print(open(b+"/job/o%d"%spool).read())
