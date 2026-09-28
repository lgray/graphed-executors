"""Prototype of m68b's stdlib-only ``announce.py`` (python3.9-compatible; run inside a job).

    python3 announce_proto.py service.json

service.json: {"argv": [...], "env": {}, "check": "http:/"|"tcp"|"grpc:...", "ports": [lo, hi],
               "key": str, "url": str | null, "watch": <dag dir> | null, "secret": <file>,
               "python": str, "timeout_s": float}
Attached mode (url set): announce once to url. DAG mode (watch set): read <watch>/driver.url and
<watch>/graphed-secret, announce again whenever that (url, secret) pair changes.
Exit: the child's returncode after it ends; 3 when no port of the range yields a ready child.
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
    s = socket.socket()
    try:
        s.bind(("", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def post(url, secret_hex, body):
    sig = hmac.new(bytes.fromhex(secret_hex), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url.rstrip("/") + "/announce", data=body, method="POST",
                                 headers={SIG_HEADER: sig})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def main():
    cfg = json.load(open(sys.argv[1]))
    ident = host_identity()
    lo, hi = cfg["ports"]
    child, port, reason = None, None, "no free port in %d-%d" % (lo, hi)
    for cand in range(lo, hi + 1):
        if not free(cand):
            log("port %d taken, next" % cand)
            continue
        argv = [a.format(port=cand, host=ident, python=cfg["python"]) for a in cfg["argv"]]
        child = subprocess.Popen(argv, env={**os.environ, **cfg.get("env", {})})
        deadline = time.monotonic() + cfg["timeout_s"]
        while time.monotonic() < deadline:
            if child.poll() is not None:
                reason = "child exited %s on port %d" % (child.returncode, cand)
                break
            reason = self_check(cfg["check"], ident, cand)
            if reason is None and child.poll() is None:
                port = cand
                break
            time.sleep(0.5)
        if port is not None:
            break
        if child.poll() is None:
            child.kill()
            child.wait()
        log("port %d: %s" % (cand, reason))
    if port is None:
        log("not ready: %s" % reason)
        return 3
    body = ("%s %s:%d %s" % (cfg["key"], ident, port, ident)).encode()
    log("ready pid=%d body=%r" % (child.pid, body.decode()))
    signal.signal(signal.SIGTERM, lambda *_: (child.terminate(), child.wait(), sys.exit(143)))
    last = None
    while child.poll() is None:
        if cfg.get("watch"):
            try:
                url = open(os.path.join(cfg["watch"], "driver.url")).read().strip()
                secret = open(os.path.join(cfg["watch"], "graphed-secret")).read().strip()
            except OSError:
                url = None
        else:
            url, secret = cfg["url"], open(cfg["secret"]).read().strip()
        if url and (url, secret) != last:
            try:
                log("announce to %s -> %s" % (url, post(url, secret, body)))
                last = (url, secret)
            except (urllib.error.URLError, OSError) as exc:
                log("announce to %s failed: %r" % (url, exc))
        time.sleep(1.0)
    log("child exited %s" % child.returncode)
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
