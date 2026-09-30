"""m69b-r1: graphed d0ad16b's require_bound against a process bound as §5.1 "Served process" states it
(a missing server -> UnboundService; tls/http schemes and shared endpoints refused), over a plan on 1 and 2 servers.

Run: ~/vibe-coding/cloud/graphed-histogram/.venv/bin/python probe_require_bound_shared_rv1.py
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from graphed.core import Partition
from graphed.core.execution import Plan, Task
from graphed.services import ServiceSpec, UnboundService, require_bound, split_endpoint


@dataclass(frozen=True)
class Served:
    servers: tuple[str, ...]
    endpoints: dict[str, str] | None = None

    def __call__(self, partition: Partition, resources: Any) -> int:
        return 1

    def bind_services(self, endpoints: dict[str, str]) -> "Served":
        have = {**(self.endpoints or {}), **{n: e for n, e in endpoints.items() if n in self.servers}}
        missing = [n for n in self.servers if n not in have]
        if missing:
            raise UnboundService(*missing)
        for e in have.values():
            if split_endpoint(e)[0] != "tcp" and split_endpoint(e)[0] != "grpc":
                raise ValueError(f"histserv dials plaintext only: {e}")
        if len(set(have.values())) < len(have):
            raise ValueError(f"two histserv servers bound to one endpoint: {have}")
        return replace(self, endpoints=have)


for n in (1, 2):
    names = tuple(f"histserv-{i}" for i in range(n))
    plan = Plan(process=Served(names), combine=lambda a, b: a + b, empty=int,
                tasks=(Task(0, Partition("f.root", "Events", 0, 1)),),
                services=tuple(ServiceSpec(s, "histserv") for s in names))
    try:
        require_bound(plan)
        print(f"{n} server(s): require_bound returned")
    except Exception as e:  # noqa: BLE001
        print(f"{n} server(s): require_bound raised {type(e).__name__}: {e}")
    bound = replace(plan, process=plan.process.bind_services({s: f"tcp://127.0.0.1:{10000 + i}" for i, s in enumerate(names)}))
    require_bound(bound)
    print(f"{n} server(s), bound to distinct endpoints: require_bound returned")
