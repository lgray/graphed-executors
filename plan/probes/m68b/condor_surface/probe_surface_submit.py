"""Surface area S: submit description semantics (executable/initialdir, arguments, environment, input and output
transfer, MY.* attributes, request_gpus). Needs the sim-GPU line in the pool (probes/m68b/sim_gpu.config) for S13.

Pool: `echo 'NUM_CPUS = 40' > /etc/condor/config.d/98-cpus` + `condor_restart -daemon startd` in surf-pool first (4 real CPUs would
starve concurrent jobs/SERVICE nodes).
Run: docker exec -u submituser -w /home/submituser surf-pool python3 /probes/condor_surface/probe_surface_submit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import (INSPECT, base, final, header, hist, listdir, q, read, rm, say, schedd, script, short,
                         submit, wait_gone, wait_status, write, fresh, HOME, htc)

header("probe_surface_submit")

# ---------- S1 executable relative vs initialdir; S2 executable basename in scratch
d = fresh("s1")
script(os.path.join(d, "svc.sh"), "echo ran; echo \"argv0=$0 args=$*\"\n")
os.chdir(HOME)  # svc.sh is NOT in cwd
c_rel = submit(base(d, executable="svc.sh", arguments="service.json"))
c_abs = submit(base(d, executable=os.path.join(d, "svc.sh"), arguments="service.json"))
a = wait_status(c_rel, (5,), 60)
say("S1a relative executable, initialdir holds it, submit cwd does not:", "JobStatus", a and a.get("JobStatus"),
    "HoldReasonCode", a and a.get("HoldReasonCode"), "|", short(a and a.get("HoldReason"), 160))
rm(c_rel)
wait_gone(c_abs)
say("S1b absolute executable:", final(c_abs, ("JobStatus", "ExitCode")), "out:", read(os.path.join(d, "job.out")).split("\n")[:2])
say("S2 argv0 is the executable's own basename in scratch (not condor_exec.exe); arguments passed verbatim")

# ---------- S3 initialdir missing at submit; output/error/log paths
d3 = os.path.join(fresh("s3"), "run-nonce-1")  # not created
try:
    c = submit(base(d3, executable="/bin/true"))
    say("S3a initialdir absent at submit: accepted cluster", c, q(c, ("JobStatus", "HoldReasonCode", "HoldReason")))
    rm(c)
except Exception as e:
    say("S3a initialdir absent at submit: submit raised", type(e).__name__, short(str(e), 200))
d3b = fresh("s3b")
c = submit(base(d3b, executable="/bin/echo", arguments="hello", output="sub/dir/job.out", error="sub/dir/job.err",
                log="logs/job.log"))
say("S3b just after submit, initialdir holds:", listdir(d3b), "sub/dir:", listdir(os.path.join(d3b, "sub/dir")))
wait_gone(c)
say("S3c after exit:", final(c, ("JobStatus", "ExitCode", "HoldReasonCode")), "sub/dir:", listdir(os.path.join(d3b, "sub/dir")),
    "logs:", listdir(os.path.join(d3b, "logs")))

d3d = fresh("s3d")
c = submit(base(d3d, executable="/bin/sleep", arguments="20", output="service.out", error="service.err", log="service.log"))
say("S3d just after submit (output/error in initialdir itself):", {f: os.path.getsize(os.path.join(d3d, f)) for f in listdir(d3d)})
rm(c)

# ---------- S4 environment of a job without getenv / environment
d = fresh("s4")
script(os.path.join(d, "env.sh"), "env | sort\ncommand -v python3 || echo no-python3\n")
c = submit(base(d, executable=os.path.join(d, "env.sh")))
wait_gone(c)
out = read(os.path.join(d, "job.out"))
names = sorted(l.split("=", 1)[0] for l in out.splitlines() if "=" in l)
say("S4a job env (no getenv) names:", names)
say("S4d TMPDIR/TMP/TEMP/HOME:", [l for l in out.splitlines() if l.split("=")[0] in ("TMPDIR", "TMP", "TEMP", "HOME")])
say("S4b PATH:", [l for l in out.splitlines() if l.startswith("PATH=")], "python3:", out.splitlines()[-1])
script(os.path.join(d, "pyexe.sh"), """exec python3 -c "import sys, os; print(repr(sys.executable), repr(os.environ.get('PATH')))"\n""")
c = submit(base(d, executable=os.path.join(d, "pyexe.sh"), output="pyexe.out"))
wait_gone(c)
say("S4e `exec python3` from sh in a job: sys.executable, os.environ PATH =", read(os.path.join(d, "pyexe.out")).strip(), read(os.path.join(d, "job.err")).strip()[:200])
c = submit(base(d, executable=os.path.join(d, "env.sh"), environment='"A=1 B=\'x y\'"', getenv="FOO*", output="job2.out"),)
wait_gone(c)
say("S4c environment= new syntax + getenv matchlist:", [l for l in read(os.path.join(d, "job2.out")).splitlines() if l[:2] in ("A=", "B=")])

# ---------- S5 transfer_input_files shapes (one job) + S6 collisions + S7 missing
d = fresh("s5")
src = fresh("s5src")
write(os.path.join(src, "file.txt"), "f\n")
write(os.path.join(src, "models", "m1", "config.pbtxt"), "cfg\n")
write(os.path.join(src, "models", "top.txt"), "top\n")
os.symlink(os.path.join(src, "file.txt"), os.path.join(src, "models", "link_to_file"))
write(os.path.join(src, "dirlinks", "real", "r.txt"), "r\n")
os.symlink(os.path.join(src, "dirlinks", "real"), os.path.join(src, "dirlinks", "link_to_dir"))
write(os.path.join(src, "slashdir", "inner.txt"), "inner\n")
os.makedirs(os.path.join(src, "emptydir"))
os.symlink(os.path.join(src, "file.txt"), os.path.join(src, "filelink"))
write(os.path.join(src, "with space", "s.txt"), "s\n")
inputs = [os.path.join(src, "file.txt"), os.path.join(src, "models"), os.path.join(src, "slashdir") + "/",
          os.path.join(src, "emptydir"), os.path.join(src, "filelink"), "file.txt" if False else os.path.join(src, "with space")]
script(os.path.join(d, "ls.sh"), "find . -mindepth 1 -maxdepth 4 ! -path './.*' | sort; for f in filelink models/link_to_file; do [ -L $f ] && echo \"$f is-symlink\" || echo \"$f not-symlink\"; done\n")
c = submit(base(d, executable=os.path.join(d, "ls.sh"), transfer_input_files=",".join(inputs)))
r = wait_gone(c, 90)
fa = final(c, ("JobStatus", "ExitCode", "HoldReasonCode", "HoldReason"))
if r is None:
    a = q(c, ("JobStatus", "HoldReasonCode", "HoldReason")); rm(c)
    say("S5 shapes job still queued:", a.get("JobStatus"), a.get("HoldReasonCode"), short(a.get("HoldReason")))
else:
    say("S5 shapes job:", fa)
    for line in read(os.path.join(d, "job.out")).splitlines():
        say("S5   ", line)

# a directory holding a symlink to a directory
d = fresh("s5a")
script(os.path.join(d, "ls.sh"), "find . -mindepth 1 -maxdepth 3 ! -path './.*' | sort | tr '\\n' ' '\n")
c = submit(base(d, executable=os.path.join(d, "ls.sh"), transfer_input_files=os.path.join(src, "dirlinks")))
a = wait_status(c, (4, 5), 60) or {}
if q(c) is None or a.get("JobStatus") == 4:
    wait_gone(c)
    say("S5a directory holding a symlink to a directory:", final(c, ("JobStatus", "ExitCode")), read(os.path.join(d, "job.out")).strip())
else:
    say("S5a directory holding a symlink to a directory: held", a.get("HoldReasonCode"), short(a.get("HoldReason"), 400))
    rm(c)

# symlink to a directory at top level
os.symlink(os.path.join(src, "models"), os.path.join(src, "models_link"))
d = fresh("s5b")
script(os.path.join(d, "ls.sh"), "find . -mindepth 1 -maxdepth 3 ! -path './.*' | sort\n")
c = submit(base(d, executable=os.path.join(d, "ls.sh"), transfer_input_files=os.path.join(src, "models_link")))
a = wait_status(c, (4, 5), 60) or {}
if q(c) is None or a.get("JobStatus") == 4:
    wait_gone(c)
    say("S5b top-level symlink to a directory:", final(c, ("JobStatus", "ExitCode")), read(os.path.join(d, "job.out")).split())
else:
    say("S5b top-level symlink to a directory: held", a.get("HoldReasonCode"), short(a.get("HoldReason"), 400))
    rm(c)

# comma in a path: the list is comma-separated
d = fresh("s5c")
write(os.path.join(src, "a,b.txt"), "comma\n")
try:
    c = submit(base(d, executable="/bin/ls", arguments="-A", transfer_input_files=os.path.join(src, "a,b.txt")))
    a = wait_status(c, (4, 5), 60) or {}
    say("S5c input path with a comma:", "JobStatus", a.get("JobStatus"), a.get("HoldReasonCode"), short(a.get("HoldReason"), 400))
    rm(c)
except Exception as e:
    say("S5c input path with a comma: submit raised", type(e).__name__, short(str(e)))

# S6 collisions: duplicate basename; input named like the executable; inputs named like condor's own entries
d = fresh("s6")
write(os.path.join(src, "one", "service.json"), "USER-ONE\n")
write(os.path.join(src, "two", "service.json"), "USER-TWO\n")
write(os.path.join(d, "service.json"), "JOB-OWN\n")
script(os.path.join(d, "svc.sh"), "echo \"service.json=$(cat service.json)\"; cat svc.sh | head -2 | tail -1\n")
write(os.path.join(src, "three", "svc.sh"), "#!/bin/sh\necho USER-SVC-SH\n", 0o755)
c = submit(base(d, executable=os.path.join(d, "svc.sh"),
                transfer_input_files="service.json,%s,%s" % (os.path.join(src, "one", "service.json"), os.path.join(src, "two", "service.json"))))
wait_gone(c, 60)
say("S6a job's service.json then two user service.json (list order job,one,two):", final(c, ("JobStatus", "ExitCode")),
    read(os.path.join(d, "job.out")).split("\n")[0])
c = submit(base(d, executable=os.path.join(d, "svc.sh"), output="job-b.out",
                transfer_input_files=os.path.join(src, "three", "svc.sh")))
wait_gone(c, 60)
say("S6b input with the executable's basename:", final(c, ("JobStatus", "ExitCode", "HoldReasonCode")),
    read(os.path.join(d, "job-b.out")).replace("\n", " | "))
for name in (".job.ad", ".machine.ad", "_condor_stdout", "tmp", "var"):
    p = os.path.join(src, "collide", name)
    if name in ("tmp", "var"):
        write(os.path.join(p, "USERFILE"), "user\n")
    else:
        write(p, "USER-%s\n" % name)
    dd = fresh("s6-" + name.strip("._"))
    script(os.path.join(dd, "c.sh"), "echo \"JOB_AD=$_CONDOR_JOB_AD\"; ls -A | tr '\\n' ' '; echo; "
           "if [ -d '%s' ]; then echo \"dir %s: $(ls -A '%s' | tr '\\n' ' ')\"; else echo \"file %s: $(head -c 60 '%s' | tr '\\n' ' ')\"; fi; echo 'stdout-line'\n"
           % (name, name, name, name, name))
    c = submit(base(dd, executable=os.path.join(dd, "c.sh"), transfer_input_files=p))
    wait_gone(c, 60)
    say("S6c input named %-15s" % name, final(c, ("JobStatus", "ExitCode", "HoldReasonCode")), "|",
        read(os.path.join(dd, "job.out")).replace("\n", " | ")[:300])

# S7 missing input -> hold 13
d = fresh("s7")
c = submit(base(d, executable="/bin/true", transfer_input_files=os.path.join(src, "no-such-models")))
a = wait_status(c, (5,), 60, ("JobStatus", "HoldReasonCode", "HoldReasonSubCode", "HoldReason")) or {}
say("S7 missing input:", "JobStatus", a.get("JobStatus"), "HoldReasonCode", a.get("HoldReasonCode"), "HoldReasonSubCode", a.get("HoldReasonSubCode"), "|", short(a.get("HoldReason"), 400))
rm(c)

# S8 preserve_relative_paths: can condor itself land inputs in a subdir (an alternative to moving them)?
d = fresh("s8")
write(os.path.join(d, "service", "models", "m.txt"), "m\n")
write(os.path.join(d, "service", "cfg.json"), "{}\n")
script(os.path.join(d, "ls.sh"), "find . -mindepth 1 -maxdepth 3 ! -path './.*' | sort | tr '\\n' ' '\n")
c = submit(base(d, executable=os.path.join(d, "ls.sh"), preserve_relative_paths="True",
                transfer_input_files="service/models,service/cfg.json,%s" % os.path.join(src, "file.txt")))
wait_gone(c, 60)
say("S8 preserve_relative_paths (relative service/models, service/cfg.json; absolute file.txt):",
    final(c, ("JobStatus", "ExitCode", "HoldReasonCode")), "|", read(os.path.join(d, "job.out")).strip())

# ---------- S9 transfer_output_files: missing output, exit codes, signals, ON_EXIT vs ON_EXIT_OR_EVICT vs ON_SUCCESS
d = fresh("s9")
cases = {
    "exit0-missing-ON_EXIT": ("exit 0", {"when_to_transfer_output": "ON_EXIT"}),
    "exit1-missing-ON_EXIT": ("exit 1", {"when_to_transfer_output": "ON_EXIT"}),
    "exit1-missing-ON_EXIT_OR_EVICT": ("exit 1", {"when_to_transfer_output": "ON_EXIT_OR_EVICT"}),
    "kill9-missing-ON_EXIT": ("kill -9 $$", {"when_to_transfer_output": "ON_EXIT"}),
    "kill9-present-ON_EXIT": ("echo r > result.pkl; kill -9 $$", {"when_to_transfer_output": "ON_EXIT"}),
    "exit3-present-ON_EXIT": ("echo r > result.pkl; exit 3", {"when_to_transfer_output": "ON_EXIT"}),
    "exit1-missing-ON_SUCCESS": ("exit 1", {"when_to_transfer_output": "ON_SUCCESS", "success_exit_code": "0"}),
    "exit3-present-ON_SUCCESS": ("echo r > result.pkl; exit 3", {"when_to_transfer_output": "ON_SUCCESS", "success_exit_code": "0"}),
}
cl = {}
for name, (body, kw) in cases.items():
    dd = os.path.join(d, name); os.makedirs(dd)
    script(os.path.join(dd, "x.sh"), body + "\n")
    cl[name] = submit(base(dd, executable=os.path.join(dd, "x.sh"), transfer_output_files="result.pkl", **kw))
for name, c in cl.items():
    a = wait_status(c, (4, 5), 90, ("JobStatus", "HoldReasonCode", "HoldReason", "ExitCode", "ExitBySignal")) or q(c, ("JobStatus",))
    if a is None or a.get("JobStatus") == 4:
        wait_gone(c, 30)
        a = final(c, ("JobStatus", "ExitCode", "ExitBySignal", "ExitSignal"))
        say("S9 %-32s left queue:" % name, a, "result.pkl back:", os.path.exists(os.path.join(d, name, "result.pkl")))
    else:
        say("S9 %-32s JobStatus %s HoldReasonCode %s | %s" % (name, a.get("JobStatus"), a.get("HoldReasonCode"), short(a.get("HoldReason"), 400)))
        rm(c)

# ---------- S10 MY.* attributes and quoting
d = fresh("s10")
c = submit(base(d, executable="/bin/true", **{"MY.SingularityImage": '"/cvmfs/x/img:1"', "MY.SendFlag": "True",
                                              "MY.Unquoted": "some_name", "+JobFlavour": '"espresso"', "JobBatchName": "graphed-service-k1",
                                              "hold": "True"}))
ad = schedd.query("ClusterId == %d" % c, ["SingularityImage", "SendFlag", "Unquoted", "JobFlavour", "JobBatchName"])[0]
say("S10 MY.* ->", {k: (repr(ad.get(k)), type(ad.get(k)).__name__) for k in ("SingularityImage", "SendFlag", "JobFlavour", "JobBatchName")},
    "unquoted MY.Unquoted = some_name evaluates to", repr(ad.eval("Unquoted")) if hasattr(ad, "eval") else ad.get("Unquoted"),
    "(expr:", str(ad.lookup("Unquoted")) if hasattr(ad, "lookup") else "?", ")")
rm(c)

# ---------- S11 request_* rendering: a float string, request_gpus = 0
d = fresh("s11")
for label, kw in (("request_cpus=1.0", {"request_cpus": "1.0"}), ("request_memory=64.0", {"request_memory": "64.0"}),
                  ("request_gpus=0", {"request_gpus": "0"})):
    try:
        c = submit(base(d, executable="/bin/true", hold="True", **kw))
        a = schedd.query("ClusterId == %d" % c, ["RequestCpus", "RequestMemory", "RequestGPUs", "Requirements"])[0]
        say("S11 %-20s accepted:" % label, {k: str(a.get(k)) for k in ("RequestCpus", "RequestMemory", "RequestGPUs")},
            "GPUs in Requirements:", "GPUs" in str(a.get("Requirements")))
        rm(c)
    except Exception as e:
        say("S11 %-20s submit raised" % label, type(e).__name__, short(str(e)))

# ---------- S12 request_gpus with the simulated GPU
d = fresh("s12")
script(os.path.join(d, "g.sh"), "env | grep -i -E 'CUDA|GPU' | sort | tr '\\n' ' '\n")
c1 = submit(base(d, executable=os.path.join(d, "g.sh"), request_gpus="1", output="g1.out"))
c2 = submit(base(d, executable=os.path.join(d, "g.sh"), request_gpus="2", output="g2.out"))
wait_gone(c1, 120)
say("S12a request_gpus=1:", final(c1, ("JobStatus", "ExitCode", "AssignedGPUs")), "| env:", read(os.path.join(d, "g1.out")).strip())
import time; time.sleep(10)
say("S12b request_gpus=2 on a one-GPU pool after 10 s:", q(c2, ("JobStatus", "NumJobStarts")))
rm(c2)
say("S-done")
