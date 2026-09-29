"""B2's in-driver leg on m68a's engine at executors 0e48380 (read-only).

Run on macOS: ``cd /private/tmp && PYTHONPATH=~/vibe-coding/cloud/code-m68b-main/src
~/vibe-coding/cloud/.venv-m68a/bin/python <this file>`` (graphed d0ad16b in that venv; the import
path resolves ``graphed_executors`` to the 0e48380 worktree). Output: ``probe_b2base_injob.txt``.

A fake in-job backend shaped as B2 plans it (``service_hosts == ("driver",)``, ``host_service`` /
``release_service`` bound from an ``announced`` map) goes through m68a's unmodified ``ServiceSet``.
Also: B2's ``SiteProfile.job_root`` inserted after ``jobs_can_submit`` into a copy of 0e48380's
``sites.py`` composes with m68a's ``__post_init__``/positional ``__reduce__``.
"""

from __future__ import annotations

import copy
import dataclasses
import http.server
import pickle
import sys
import threading
import types
from concurrent.futures import Future
from pathlib import Path

import graphed_executors
from graphed.services import Launch, ServiceSpec
from graphed_executors.submit import services as S

print("graphed_executors from", graphed_executors.__file__)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=srv.serve_forever, daemon=True).start()
ENDPOINT = f"http://127.0.0.1:{srv.server_address[1]}"


class InJob:
    """B2's in-job backend shape: announced names -> node ids; no ServiceJob."""

    def __init__(self, announced: dict[str, str], site: dict[str, str] | None = None) -> None:
        self.site_services = site or {}
        self.service_hosts = ("driver",)
        self.service_ports = None
        self.advertise_host = "127.0.0.1"
        self.calls: list[tuple[str, ...]] = []
        if announced:
            self._announced = announced
            self.host_service = self._host_service
            self.release_service = self._release_service

    def host_identity(self) -> str:
        return "driver-node"

    def _host_service(self, spec: ServiceSpec, scope: str) -> tuple[str, str, str]:
        self.calls.append(("host_service", spec.name, scope))
        if spec.name not in self._announced:
            raise ValueError(f"{spec.name!r} is not in announce_only {sorted(self._announced)}")
        return ENDPOINT, "service-node", self._announced[spec.name]

    def _release_service(self, key: str) -> None:
        self.calls.append(("release_service", key))

    def n_workers(self) -> int:
        return 1

    def submit(self, fn, *args, key: str, **_: object) -> Future:
        fut: Future = Future()
        fut.set_result(fn(*args))
        return fut

    def cancel(self, futs) -> None:
        pass


gpu = ServiceSpec("a b", "http", check="http:/", launch=Launch(argv=("x",), resources={"gpus": 1}), timeout_s=5)
imaged = ServiceSpec("img", "http", check="http:/", launch=Launch(argv=("x",), image="/cvmfs/x"), timeout_s=5)

# 1. announced GPU spec -> leg 3 cluster via host_service(spec, scope), identity from it, released by key
b = InJob({"a b": "svc0"})
ss = S.ServiceSet([gpu], b)
eps = ss.start()
st = ss.statuses()[0]
print("1 status", (st.leg, st.host, st.identity, st.endpoint == ENDPOINT), "endpoints", dict(eps))
ss.close()
print("1 calls", [c[0] + ":" + c[-1] if c[0] == "release_service" else c[:2] for c in b.calls])

# 2. an imaged spec outside announce_only -> the ValueError propagates out of start()
b = InJob({"a b": "svc0"})
try:
    S.ServiceSet([imaged], b).start()
    print("2 no raise")
except ValueError as exc:
    print("2 ValueError:", exc)

# 3. control: the site row serves the kind -> leg 2, host_service never called
b = InJob({"a b": "svc0"}, site={"http": ENDPOINT})
ss = S.ServiceSet([gpu], b)
ss.start()
print("3 status", (ss.statuses()[0].leg, ss.statuses()[0].host), "host_service calls", [c for c in b.calls if c[0] == "host_service"])
ss.close()

# 4. control: no announced -> no host_service attribute -> ServiceUnavailable naming host_service
b = InJob({})
try:
    S.ServiceSet([gpu], b).start()
except S.ServiceUnavailable as exc:
    print("4 ServiceUnavailable:", exc)

srv.shutdown()

# 5. SiteProfile.job_root after jobs_can_submit, in a copy of 0e48380's sites.py
src = (Path(graphed_executors.__file__).parent / "htcondor_backend" / "sites.py").read_text()
anchor = "    jobs_can_submit: bool = True\n"
assert src.count(anchor) == 1
mod = types.ModuleType("sites_b2")
sys.modules["sites_b2"] = mod
exec(compile(src.replace(anchor, anchor + "    job_root: str | None = None\n"), "sites_b2", "exec"), mod.__dict__)
print("5 fields", [f.name for f in dataclasses.fields(mod.SiteProfile)][-4:])
lx = dataclasses.replace(mod.SITES["lxplus"], job_root="/tmp/root")
back = pickle.loads(pickle.dumps(lx))
print("5 pickle", back == lx, back.job_root, dict(back.services), type(back.services).__name__)
lpc = dataclasses.replace(mod.SITES["lpc"], sandbox_root="/tmp/sb", services={})
print("5 replace", lpc.job_root, dict(lpc.services), dict(copy.deepcopy(mod.SITES["lpc"]).services))
