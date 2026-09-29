import os, time, htcondor2 as htc
H=os.path.expanduser("~"); s=htc.Schedd()
def run(tag, jobdir, tif, setup):
    os.makedirs(jobdir+"/service",exist_ok=True); setup(jobdir)
    open(jobdir+"/look.sh","w").write("#!/bin/sh\nfind service | sort\n"); os.chmod(jobdir+"/look.sh",0o755)
    r=s.submit(htc.Submit({"executable":jobdir+"/look.sh","initialdir":jobdir,"transfer_input_files":tif,"should_transfer_files":"YES","when_to_transfer_output":"ON_EXIT","output":"o","error":"e","log":"l","request_memory":"64"}))
    c=r.cluster()
    for _ in range(60):
        q=s.query("ClusterId==%d"%c,["JobStatus","HoldReason"])
        if not q: break
        if q[0]["JobStatus"]==5: print(tag,"HELD",q[0]["HoldReason"][:200]); s.act(htc.JobAction.Remove,"ClusterId==%d"%c); return
        time.sleep(2)
    print(tag,"ran:",open(jobdir+"/o").read().split())
src=H+"/csrc"; os.makedirs(src+"/d,ir",exist_ok=True); open(src+"/d,ir/f,1","w").write("x"); open(src+"/w,t","w").write("y")
def comma_inputs(j):
    os.makedirs(j+"/service/d,ir",exist_ok=True)
    for a,b in (("d,ir/f,1","d,ir/f,1"),("w,t","w,t")):
        if not os.path.lexists(j+"/service/"+b): os.symlink(src+"/"+a, j+"/service/"+b)
j=H+"/cj1"; run("A comma-named inputs inside service/, list names <dir>/service", j, j+"/service", comma_inputs)
j=H+"/log,dir/service-k"; run("B log_dir with a comma, absolute <dir>/service", j, j+"/service", comma_inputs)
j=H+"/log,dir/service-k2"; run("C log_dir with a comma, relative 'service' (resolved against initialdir)", j, "service", comma_inputs)
