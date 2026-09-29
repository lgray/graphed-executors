"""m68b pool probe: the recipe's inputs reach the job as ONE transferred directory `service/` built on the submit
side from symlinks, so the child's cwd holds exactly the declared inputs by construction.

Run: docker run -d --name plan10-pool -v <plan>/probes/m68b:/probes htcondor/mini
     docker exec -u submituser plan10-pool python3 /probes/probe_input_dir.py > probe_input_dir.txt

The submit side makes <d>/service/ in two forms. LINKDIR: `models` a symlink to the directory /abs/src/mymodels.
MIRROR: `models/` a real directory tree mirroring /abs/src/mymodels whose files are symlinks. In both, `w.txt` ->
/abs/src/weights.bin (a file symlink, link name differs from the target's) and `service.json` -> /abs/src/user.json
(an input that shares a job file's name). transfer_input_files = service.json(the job's own),<d>/service. Legs, unspooled and
spooled: what lands in scratch, whether the links were followed (regular files/dirs, contents), and that the job's
own service.json is untouched by the input of that name.
"""
import os
import shutil
import time

import htcondor2 as htc

schedd = htc.Schedd()
H = os.path.expanduser("~")
print("condor", htc.version())


def mirror(src, dst):
    os.makedirs(dst)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for x in dirs:
            os.makedirs(os.path.join(dst, rel, x))
        for f in files:
            os.symlink(os.path.join(root, f), os.path.join(dst, rel, f))


def setup(tag, form):
    base = os.path.join(H, "p10-" + tag)
    shutil.rmtree(base, ignore_errors=True)
    src = os.path.join(base, "src")
    os.makedirs(os.path.join(src, "mymodels", "m", "1"))
    open(os.path.join(src, "mymodels", "m", "1", "model.onnx"), "w").write("ONNX")
    open(os.path.join(src, "weights.bin"), "w").write("W")
    open(os.path.join(src, "user.json"), "w").write('{"user": true}')
    d = os.path.join(base, "job")
    os.makedirs(os.path.join(d, "service"))
    if form == "linkdir":
        os.symlink(os.path.join(src, "mymodels"), os.path.join(d, "service", "models"))
    else:
        mirror(os.path.join(src, "mymodels"), os.path.join(d, "service", "models"))
    os.symlink(os.path.join(src, "weights.bin"), os.path.join(d, "service", "w.txt"))
    os.symlink(os.path.join(src, "user.json"), os.path.join(d, "service", "service.json"))
    open(os.path.join(d, "service.json"), "w").write('{"job": true}')
    open(os.path.join(d, "look.sh"), "w").write(
        "#!/bin/sh\n"
        "echo JOB service.json: $(cat service.json)\n"
        "find service | sort | while read p; do\n"
        "  if [ -L \"$p\" ]; then t=symlink; elif [ -d \"$p\" ]; then t=dir; else t=\"file:$(cat $p)\"; fi\n"
        "  echo \"  $p $t\"\n"
        "done\n")
    os.chmod(os.path.join(d, "look.sh"), 0o755)
    return d


for tag, form, spool in (("linkdir", "linkdir", False), ("mirror-plain", "mirror", False),
                         ("mirror-spool", "mirror", True)):
    d = setup(tag, form)
    desc = {"universe": "vanilla", "executable": os.path.join(d, "look.sh"), "initialdir": d,
            "transfer_input_files": "service.json," + os.path.join(d, "service"),
            "should_transfer_files": "YES", "when_to_transfer_output": "ON_EXIT", "transfer_output_files": '""',
            "output": "look.out", "error": "look.err", "log": "look.log", "request_memory": "64"}
    res = schedd.submit(htc.Submit(desc), spool=spool)
    c = res.cluster()
    if spool:
        try:
            schedd.spool(res)
        except Exception as exc:
            print("[%s] spool raised: %s" % (tag, str(exc)[:300]))
            schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
            continue
    end = time.monotonic() + 120
    while time.monotonic() < end:
        q = schedd.query("ClusterId == %d" % c, ["JobStatus", "HoldReason"])
        if not q or q[0].get("JobStatus") == 4:
            break
        if q[0].get("JobStatus") == 5 and "Spooling" not in str(q[0].get("HoldReason")):
            print("[%s] held:" % tag, q[0].get("HoldReason"))
            schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
            break
        time.sleep(2)
    if spool:
        schedd.retrieve("ClusterId == %d" % c)
        schedd.act(htc.JobAction.Remove, "ClusterId == %d" % c)
    h = list(schedd.history("ClusterId == %d" % c, ["ExitCode"], match=1)) or [{}]
    print("[%s] ExitCode %s" % (tag, h[0].get("ExitCode")))
    print(open(os.path.join(d, "look.out")).read().rstrip() if os.path.exists(os.path.join(d, "look.out")) else "(no output)")
    err = open(os.path.join(d, "look.err")).read().strip() if os.path.exists(os.path.join(d, "look.err")) else ""
    if err:
        print("[%s] stderr:" % tag, err)
