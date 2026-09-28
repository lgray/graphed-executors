"""Prototype of m68b's stdlib-only ``announce.py`` (python3.9-compatible; run inside a job).

    python3 announce_proto.py service.json

service.json: {"argv": [...], "env": {}, "check": "http:/"|"tcp"|"grpc:...", "ports": [lo, hi],
               "key": str, "url": str | null, "watch": <dag dir> | null, "secret": <file>,
               "python": str, "timeout_s": float, "lease_s": float, "beat_s": float, "inputs": [basename, ...]}
The child starts in ./service/, into which the recipe's inputs are moved; a relative {python} is made absolute.
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
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SIG_HEADER = "X-Graphed-Sig"
RUN_DIR = "service"


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


def start(cfg, ident):
    """(child, port) ready, or (None, reason)."""
    lo, hi = cfg["ports"]
    deadline = time.monotonic() + cfg["timeout_s"]
    reason = "no free port in %d-%d" % (lo, hi)
    for cand in range(lo, hi + 1):
        if not free(cand):
            log("port %d taken, next" % cand)
            continue
        python = os.path.abspath(cfg["python"]) if os.sep in cfg["python"] else cfg["python"]
        argv = [a.format(port=cand, host=ident, python=python) for a in cfg["argv"]]
        child = subprocess.Popen(argv, env={**os.environ, **cfg.get("env", {})}, cwd=RUN_DIR)
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
                child.kill()
                child.wait()
                return None, "not ready within timeout_s=%s: %s" % (cfg["timeout_s"], reason)
            time.sleep(0.5)
    return None, reason


def main():
    cfg = json.load(open(sys.argv[1]))
    ident = host_identity()
    secret_mem = None
    if not cfg.get("watch"):
        # attached: the announce secret lives in memory only, gone from the cwd the child may serve
        secret_mem = open(cfg["secret"]).read().strip()
        os.unlink(cfg["secret"])
    # the child runs in RUN_DIR holding only the recipe's inputs: nothing else in scratch (a ticket cache, the
    # job ad, our files) is in the cwd it may serve
    os.makedirs(RUN_DIR, exist_ok=True)
    for name in cfg.get("inputs", []):
        if os.path.exists(name):
            os.rename(name, os.path.join(RUN_DIR, name))
    child, port = start(cfg, ident)
    if child is None:
        log("not ready: %s" % port)
        return 3
    body = ("%s %s:%d %s" % (cfg["key"], ident, port, ident)).encode()
    log("ready pid=%d body=%r" % (child.pid, body.decode()))

    def stop(*_):
        child.terminate()
        child.wait()
        sys.exit(143)

    signal.signal(signal.SIGTERM, stop)
    last, last_ok, announced = None, time.monotonic(), False
    while child.poll() is None:
        if cfg.get("watch"):
            try:
                url = open(os.path.join(cfg["watch"], "driver.url")).read().strip()
                secret = open(os.path.join(cfg["watch"], "graphed-secret")).read().strip()
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
            child.terminate()
            child.wait()
            return 0
        time.sleep(cfg["beat_s"] if announced else 1.0)
    log("child exited %s" % child.returncode)
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
