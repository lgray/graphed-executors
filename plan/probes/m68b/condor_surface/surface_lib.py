"""Shared helpers for the m68b HTCondor surface probes. Runs INSIDE an htcondor/mini container as submituser:

  docker run -d --name surf-<x> -v <repo>/plan/probes/m68b:/probes htcondor/mini
  docker exec -u submituser -w /home/submituser surf-<x> python3 /probes/condor_surface/probe_surface_<area>.py

Every probe prints `<ROW-ID> <observation>` lines so RESULTS.md can cite a row by id.
"""
import os
import shutil
import stat
import sys
import time

import htcondor2 as htc

schedd = htc.Schedd()
HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "surf")
T0 = time.monotonic()


def say(row, *parts):
    print(row, *parts, flush=True)


def header(title):
    say("#", title)
    say("#", htc.version())
    for k in ("STARTER_NESTED_SCRATCH", "MOUNT_UNDER_SCRATCH", "PERIODIC_EXPR_INTERVAL", "DAGMAN_USE_STRICT"):
        say("#", k, "=", htc.param.get(k))


def fresh(name):
    d = os.path.join(ROOT, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode is not None:
        os.chmod(path, mode)
    return path


def script(path, body):
    return write(path, "#!/bin/sh\n" + body, 0o755)


# prints what a job sees of its sandbox; stdout comes back as the job's `output`
INSPECT = r"""
echo "pwd=$(pwd)"
echo "_CONDOR_SCRATCH_DIR=$_CONDOR_SCRATCH_DIR"
echo "_CONDOR_JOB_AD=$_CONDOR_JOB_AD"
echo "_CONDOR_MACHINE_AD=$_CONDOR_MACHINE_AD"
echo "_CONDOR_CREDS=$_CONDOR_CREDS"
echo "X509_USER_PROXY=$X509_USER_PROXY"
echo "KRB5CCNAME=$KRB5CCNAME"
echo "TMPDIR=$TMPDIR TMP=$TMP TEMP=$TEMP"
echo "hostname=$(hostname) id=$(id -u)"
echo "--- ls -A scratch"; ls -A1 . | sed 's/^/  /'
echo "--- ls -A scratch/.. "; ls -A1 .. 2>&1 | sed 's/^/  /'
echo "--- find scratch (depth 3)"; find . -maxdepth 3 | sort | sed 's/^/  /'
echo "--- env names"; env | cut -d= -f1 | sort | tr '\n' ' '; echo
echo "--- PATH=$PATH HOME=$HOME"
echo "--- mounts under scratch"; grep " $(pwd)" /proc/self/mountinfo | awk '{print "  " $4 " -> " $5}'
echo "--- /tmp write"; echo probe > /tmp/surf-probe-$$ && ls -la /tmp/surf-probe-$$ | sed 's/^/  /'; find . -name "surf-probe-$$" | sed 's/^/  found in scratch: /'
"""


def base(d, **kw):
    desc = {
        "universe": "vanilla",
        "initialdir": d,
        "should_transfer_files": "YES",
        "when_to_transfer_output": "ON_EXIT",
        "transfer_output_files": '""',
        "request_memory": "64",
        "request_disk": "10240",
        "log": "job.log",
        "output": "job.out",
        "error": "job.err",
    }
    desc.update(kw)
    return desc


def submit(desc, spool=False, count=1):
    r = schedd.submit(htc.Submit(dict(desc)), count=count, spool=spool)
    if spool:
        schedd.spool(r)
    return int(r.cluster())


def q(cluster, attrs=("JobStatus",)):
    ads = list(schedd.query("ClusterId == %d" % cluster, list(attrs)))
    return ads[0] if ads else None


def hist(cluster, attrs, match=1):
    return list(schedd.history("ClusterId == %d" % cluster, list(attrs), match=match))


def wait(pred, timeout, step=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def wait_gone(cluster, timeout=180):
    t = time.monotonic()
    ok = wait(lambda: q(cluster) is None, timeout)
    return round(time.monotonic() - t, 1) if ok else None


def wait_status(cluster, statuses, timeout=180, attrs=("JobStatus", "HoldReasonCode", "HoldReason")):
    return wait(lambda: (lambda a: a if a and a.get("JobStatus") in statuses else None)(q(cluster, attrs)), timeout)


def final(cluster, attrs=("JobStatus", "ExitCode", "ExitBySignal", "ExitSignal", "NumJobStarts", "RemoveReason",
                          "HoldReasonCode", "HoldReason")):
    """The job's history ad, waiting briefly for it to be written."""
    got = wait(lambda: hist(cluster, attrs), 30, 0.5)
    return {k: got[0].get(k) for k in attrs if got[0].get(k) is not None} if got else None


def rm(cluster, reason="probe done"):
    schedd.act(htc.JobAction.Remove, "ClusterId == %d" % cluster, reason=reason)


def read(path, limit=4000):
    try:
        with open(path) as f:
            return f.read()[:limit]
    except OSError as e:
        return "<%s>" % e.__class__.__name__


def listdir(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else None


def short(reason, n=220):
    return None if reason is None else " ".join(str(reason).split())[:n]


def exe_bits(path):
    return oct(stat.S_IMODE(os.stat(path).st_mode))


def elapsed():
    return round(time.monotonic() - T0, 1)


def ensure_home():
    os.makedirs(ROOT, exist_ok=True)
    os.chdir(HOME)


ensure_home()
sys.stdout.reconfigure(line_buffering=True)
