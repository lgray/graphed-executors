"""Prototype of m68b's stdlib-only ``announce.py`` (python3.9-compatible; run inside a job).

    python3 announce_proto.py service.json

service.json: {"argv": [...], "env": {}, "check": "http:/"|"tcp"|"grpc:...", "ports": [lo, hi],
               "key": str, "url": str | null, "watch": <dag dir> | null,
               "python": str, "timeout_s": float, "lease_s": float, "beat_s": float}
The secret is not a field: attached mode reads ./graphed-secret, watch mode <watch>/graphed-secret.
The child starts in ./service/, the transferred directory holding exactly the recipe's inputs; a relative {python}
is made absolute.
Start: `timeout_s` is the whole budget. A child that exits moves on to the next port only when its port is no
longer free (another process took it after the scan); otherwise exit 3 at once naming its returncode. A child
alive but not ready at the deadline is killed: exit 3 naming the last reason.
Attached mode (url set): the secret file is read into memory and unlinked before the child starts; the lease clock starts when the child is ready; a 403 on any POST, or no 200 for
`lease_s`, is an orphan: terminate the child, exit 0. After the first 200 it re-POSTs every `beat_s`.
DAG mode (watch set): read <watch>/driver.url and <watch>/graphed-secret each second and announce again whenever
that (url, secret) pair changes; no orphan rule (DAGMan owns the node).
Exit otherwise: the child's returncode.
"""

import hashlib
import hmac
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SIG_HEADER = "X-Graphed-Sig"
RUN_DIR = "service"
SECRET_FILE = "graphed-secret"


def log(msg):
    print("[announce %s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def host_identity():
    path = os.environ.get("_CONDOR_MACHINE_AD")
    if path and os.path.isfile(path):
        for line in open(path).read().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "Machine":
                return value.strip().strip('"')
    return socket.getfqdn()


def self_check(check, host, port):
    """None = ready. http: as check_ready (2xx, content-type not application/grpc*); tcp/grpc: connect."""
    try:
        if check.startswith("http:"):
            with urllib.request.urlopen("http://%s:%d%s" % (host, port, check[5:] or "/"), timeout=5) as r:
                ctype = r.headers.get("Content-Type", "")
                if 200 <= r.status < 300 and not ctype.startswith("application/grpc"):
                    return None
                return "status %s content-type %s" % (r.status, ctype)
        socket.create_connection((host, port), timeout=5).close()
        return None
    except Exception as exc:
        return repr(exc)


def free(port):
    """A bind with SO_REUSEADDR: refused by a listener, not by a TIME_WAIT the self-check itself left behind."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def post(url, secret_hex, body):
    """HTTP status of a signed POST to <url>/announce; None when nothing answered."""
    sig = hmac.new(bytes.fromhex(secret_hex), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url.rstrip("/") + "/announce", data=body, method="POST",
                                 headers={SIG_HEADER: sig})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return None


class _Stop(BaseException):
    """Raised by the SIGTERM handler into the main thread; the main thread then does the one reap."""


CHILD = [None]  # the child being started or served, for the one reap


def reap(child):
    """The one bounded reap every exit path uses: terminate, wait at most 5 s, kill."""
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def hard_reap(pid):
    """The reap after a SIGTERM: on the pid, never through Popen (whose waitpid lock an interrupted poll/wait may
    have leaked): SIGTERM, poll os.waitpid(WNOHANG) for at most 5 s, then SIGKILL and a blocking os.waitpid."""
    # after the None return, so the in-process legs' reaped path still runs on Windows (only its mypy needs the guard)
    if pid is None or sys.platform == "win32":
        return
    try:
        os.kill(pid, signal.SIGTERM)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if os.waitpid(pid, os.WNOHANG) != (0, 0):
                return
            time.sleep(0.05)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        return  # already exited and reaped


def on_sigterm(*_):
    # never wait here: the interrupted main thread may hold Popen's waitpid lock. Ignore further SIGTERMs and
    # unwind the main thread, which reaps.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise _Stop


def unblock_sigterm():
    if sys.platform != "win32":  # Unix-only names; announce.py itself runs only in a Linux job
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})


def start(cfg, ident):
    """(child, port) ready, or (None, reason)."""
    lo, hi = cfg["ports"]
    deadline = time.monotonic() + cfg["timeout_s"]
    reason = "no free port in %d-%d" % (lo, hi)
    for cand in range(lo, hi + 1):
        if not free(cand):
            log("port %d taken, next" % cand)
            continue
        # {python} is resolved against the JOB dir (announce.py's cwd, where env/ is): never sys.executable (empty
        # for a bare `python3` in a job without PATH); a path with a separator is made absolute here, a bare name is
        # resolved on PATH or os.defpath, else left bare. A literal argv[0] is left as written: Popen resolves a
        # relative one against cwd=service/, where the recipe's inputs are.
        python = (os.path.abspath(cfg["python"]) if os.sep in cfg["python"]
                  else shutil.which(cfg["python"], path=os.environ.get("PATH", os.defpath)) or cfg["python"])
        argv = [a.format(port=cand, host=ident, python=python) for a in cfg["argv"]]
        # SIGTERM is blocked while the child is created and recorded, so a removal cannot land between the two
        if sys.platform != "win32":
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        try:
            # the child must not inherit the blocked mask (it would then ignore condor's SIGTERM)
            child = subprocess.Popen(argv, env={**os.environ, **cfg.get("env", {})}, cwd=RUN_DIR,
                                     preexec_fn=unblock_sigterm)
            CHILD[0] = child
        except OSError as exc:
            return None, "cannot start %s: %r" % (argv[0], exc)
        finally:
            unblock_sigterm()
        while True:
            if child.poll() is not None:
                if free(cand):
                    return None, "child exited %s on port %d" % (child.returncode, cand)
                log("port %d taken after the scan (child exited %s), next" % (cand, child.returncode))
                break
            reason = self_check(cfg["check"], ident, cand)
            if reason is None and child.poll() is None:
                return child, cand
            if time.monotonic() >= deadline:
                reap(child)
                return None, "not ready within timeout_s=%s: %s" % (cfg["timeout_s"], reason)
            time.sleep(0.5)
    return None, reason


def main():
    signal.signal(signal.SIGTERM, on_sigterm)
    try:
        return serve()
    except _Stop:
        # a SIGTERM (condor's removal, sent to the whole family) at any point, a reap in progress included: the
        # one bounded reap, then leave through sys.exit so coverage saves its data
        # a child Popen already reaped (returncode set) is not signalled: its pid may be reused
        child = CHILD[0]
        hard_reap(child.pid if child is not None and child.returncode is None else None)
        log("SIGTERM: reaped")
        sys.exit(143)


def serve():
    cfg = json.load(open(sys.argv[1]))
    ident = host_identity()
    secret_mem = None
    if not cfg.get("watch"):
        # attached: the announce secret lives in memory only, gone from the cwd the child may serve
        secret_mem = open(SECRET_FILE).read().strip()
        os.unlink(SECRET_FILE)
    # the child runs in RUN_DIR, which arrived as ONE transferred directory holding exactly the recipe's inputs;
    # nothing else in scratch (a ticket cache, the job ad, our files) is in the cwd it may serve
    if os.path.ismount(RUN_DIR):
        log("not ready: %s is a mount point" % RUN_DIR)
        return 3
    os.makedirs(RUN_DIR, exist_ok=True)  # a recipe without inputs transfers no directory
    child, port = start(cfg, ident)
    if child is None:
        log("not ready: %s" % port)
        return 3
    body = ("%s %s:%d %s" % (cfg["key"], ident, port, ident)).encode()
    log("ready pid=%d body=%r" % (child.pid, body.decode()))

    last, last_ok, announced = None, time.monotonic(), False
    while child.poll() is None:
        if cfg.get("watch"):
            try:
                url = open(os.path.join(cfg["watch"], "driver.url")).read().strip()
                secret = open(os.path.join(cfg["watch"], SECRET_FILE)).read().strip()
            except OSError:
                url = None
            if url and (url, secret) != last:
                status = post(url, secret, body)
                log("announce to %s -> %s" % (url, status))
                if status == 200:
                    last = (url, secret)
            time.sleep(1.0)
            continue
        status = post(cfg["url"], secret_mem, body)
        if status == 200:
            if not announced:
                log("announced to %s" % cfg["url"])
            announced, last_ok = True, time.monotonic()
        elif status == 403 or time.monotonic() - last_ok > cfg["lease_s"]:
            log("orphaned (%s, last 200 %.1fs ago): stopping the service" % (status, time.monotonic() - last_ok))
            reap(child)
            return 0
        time.sleep(cfg["beat_s"] if announced else 1.0)
    log("child exited %s" % child.returncode)
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
