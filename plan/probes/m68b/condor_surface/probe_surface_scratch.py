"""Surface area X: the execute scratch directory — what condor itself puts there, and where credentials, ads and
/tmp land — under one EP configuration. probe_surface_scratch.sh runs it across configurations (label = argv[1]).

Jobs:
  plain   an inspect job with one input file and one input dir
  proxy   x509userproxy = <submit dir>/x509up_u<uid> (a self-signed cert+key, which is all condor_submit reads)
  cred    MY.SendCredential = True (no credd/credmon on minicondor)
  tmpin   an input directory named `tmp` (collides with MOUNT_UNDER_SCRATCH's tmp/ when that is active)
  sing    MY.SingularityImage = "/opt/img" (a directory image; only in configs that enable SINGULARITY_JOB)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import INSPECT, base, final, fresh, header, q, read, rm, say, script, short, submit, wait_gone, wait_status, write, htc

label = sys.argv[1]
jobs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["plain", "proxy", "cred", "tmpin"]
header("probe_surface_scratch config=%s" % label)
for k in ("SINGULARITY_JOB", "SINGULARITY_TARGET_DIR", "MOUNT_PRIVATE_DEV_SHM"):
    say("#", k, "=", htc.param.get(k))

src = fresh("x-src-" + label)
write(os.path.join(src, "in.txt"), "in\n")
write(os.path.join(src, "models", "m.txt"), "m\n")
write(os.path.join(src, "tmp", "USERFILE"), "user\n")
proxy = os.path.join(src, "x509up_u%d" % os.getuid())
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", proxy + ".key", "-out", proxy + ".crt",
                "-days", "1", "-subj", "/CN=surface-probe"], check=True, capture_output=True)
with open(proxy, "w") as f:
    f.write(open(proxy + ".crt").read() + open(proxy + ".key").read())
os.chmod(proxy, 0o600)

cases = {
    "plain": {"transfer_input_files": "%s,%s" % (os.path.join(src, "in.txt"), os.path.join(src, "models"))},
    "proxy": {"x509userproxy": proxy, "transfer_input_files": os.path.join(src, "in.txt")},
    "cred": {"MY.SendCredential": "True", "transfer_input_files": os.path.join(src, "in.txt")},
    "tmpin": {"transfer_input_files": os.path.join(src, "tmp")},
    "sing": {"MY.SingularityImage": '"/opt/img"', "transfer_input_files": os.path.join(src, "in.txt")},
    "singall": {"MY.SingularityImage": '"/opt/img"', "x509userproxy": proxy,
                "transfer_input_files": "%s,%s" % (os.path.join(src, "in.txt"), os.path.join(src, "tmp"))},
}
for name in jobs:
    kw = cases[name]
    d = fresh("x-%s-%s" % (label, name))
    body = INSPECT + ("echo '--- tmp/ contents'; ls -A tmp 2>&1 | sed 's/^/  /'; echo '--- /tmp has USERFILE?'; ls /tmp/USERFILE 2>&1 | sed 's/^/  /'\n"
                      if name in ("tmpin", "singall") else "")
    script(os.path.join(d, "inspect.sh"), body)
    try:
        c = submit(base(d, executable=os.path.join(d, "inspect.sh"), **kw))
    except Exception as e:
        say("X[%s/%s] submit raised" % (label, name), type(e).__name__, short(str(e), 300))
        continue
    gone = wait_gone(c, 90)
    if gone is None:
        a = q(c, ("JobStatus", "HoldReasonCode", "HoldReason", "NumJobStarts"))
        say("X[%s/%s] not done after 90 s:" % (label, name), dict(JobStatus=a.get("JobStatus"), HoldReasonCode=a.get("HoldReasonCode"),
                                                                NumJobStarts=a.get("NumJobStarts")), short(a.get("HoldReason"), 250))
        ana = subprocess.run(["condor_q", "-better-analyze", str(c)], capture_output=True, text=True).stdout
        for l in [l for l in ana.splitlines() if l.strip() and any(w in l for w in ("reject", "match", "Hold", "credential", "Cred", "not", "run"))][:8]:
            say("X[%s/%s]   better-analyze: %s" % (label, name, l.strip()[:200]))
        if name == "sing":
            log = subprocess.run("grep -h -E 'singularity|apptainer' /var/log/condor/StarterLog.slot* 2>/dev/null | tail -4", shell=True, capture_output=True, text=True).stdout
            for l in log.splitlines():
                say("X[%s/%s]   StarterLog: %s" % (label, name, l[18:].strip()[:260]))
        rm(c)
        continue
    say("X[%s/%s] final:" % (label, name), final(c, ("JobStatus", "ExitCode", "HoldReasonCode")))
    for line in read(os.path.join(d, "job.out"), 12000).splitlines():
        say("X[%s/%s]   %s" % (label, name, line))
    err = read(os.path.join(d, "job.err")).strip()
    if err:
        say("X[%s/%s] stderr: %s" % (label, name, short(err, 300)))
say("X-done", label)
