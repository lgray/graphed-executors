# r18-B1: a relative transfer_input_files entry that is a file symlink in initialdir (env.tgz -> <log_dir>/env.tgz,
# absolute target), beside the relative 'service' mirror; log_dir with and without a comma; spooled and unspooled.
import os, time, tarfile, io, htcondor2 as htc
H=os.path.expanduser("~"); s=htc.Schedd()
def mk_tgz(p):
    with tarfile.open(p,"w:gz") as t:
        data=b"venv-marker\n"; ti=tarfile.TarInfo("env/marker"); ti.size=len(data); t.addfile(ti,io.BytesIO(data))
def run(tag, logdir, spool):
    os.makedirs(logdir,exist_ok=True); mk_tgz(logdir+"/env.tgz")
    j=logdir+"/service-k%d"%int(spool); os.makedirs(j+"/service",exist_ok=True)
    open(H+"/inp.txt","w").write("input\n")
    if not os.path.lexists(j+"/service/inp.txt"): os.symlink(H+"/inp.txt", j+"/service/inp.txt")
    if not os.path.lexists(j+"/env.tgz"): os.symlink(logdir+"/env.tgz", j+"/env.tgz")
    open(j+"/look.sh","w").write("#!/bin/sh\n[ -L env.tgz ] && echo env.tgz-is-symlink || echo env.tgz-regular; tar xzf env.tgz && cat env/marker; cat service/inp.txt\n"); os.chmod(j+"/look.sh",0o755)
    r=s.submit(htc.Submit({"executable":j+"/look.sh","initialdir":j,"transfer_input_files":"env.tgz,service","should_transfer_files":"YES","when_to_transfer_output":"ON_EXIT","output":"o","error":"e","log":"l","request_memory":"64","transfer_output_files":'""'}),spool=spool)
    if spool: s.spool(r)
    c=r.cluster()
    for _ in range(90):
        q=s.query("ClusterId==%d"%c,["JobStatus","HoldReason","HoldReasonCode"])
        if not q: break
        if q[0]["JobStatus"]==5 and q[0].get("HoldReasonCode")!=16: print(tag,"HELD",q[0]["HoldReason"][:250]); s.act(htc.JobAction.Remove,"ClusterId==%d"%c); return
        if q[0]["JobStatus"]==4 and spool:
            s.retrieve("ClusterId==%d"%c); s.act(htc.JobAction.Remove,"ClusterId==%d"%c); break
        time.sleep(2)
    print(tag,"spool=%s"%spool,"ran:",open(j+"/o").read().split(), "| stderr:", open(j+"/e").read().strip()[:200])
for spool in (False, True):
    run("plain log_dir", H+"/logdir", spool)
    run("comma log_dir", H+"/log,dir2", spool)
