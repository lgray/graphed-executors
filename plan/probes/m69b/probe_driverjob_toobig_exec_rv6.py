"""A driver job (in_job) whose slot Memory is 100 MiB resolves an image-less 200 MiB service. htcondor.rst
"Schedulability": a service that does not fit beside the driver "goes to the cluster ...; a backend with no
cluster host refuses it with ServiceUnavailable, whose legs["managed"] names the sizes and the limit". A driver
job has no cluster host; with a SERVICE node for another spec, its host_service is `_host_announced`.
PYTHONPATH=<tree>/src; argv[1] = a scratch dir."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from graphed.services import Launch, ServiceSpec

from graphed_executors.htcondor_backend import HTCondorBackend
from graphed_executors.htcondor_backend.sites import SITES
from graphed_executors.submit.services import ServiceSet

root = Path(sys.argv[1])
ad = root / ".machine.ad"
ad.write_text('Machine = "127.0.0.1"\nMemory = 100\n')
os.environ["_CONDOR_MACHINE_AD"] = str(ad)


class NoPilots:
    def start(self, url: str, secret: bytes, n: int) -> None:
        pass

    def stop(self) -> None:
        pass

    def alive(self) -> int:
        return 0


small = ServiceSpec("small", "http", check="http:/", ports=(40000, 40010),
                    launch=Launch(argv=("serve", "{port}"), resources={"memory_mb": 200}), timeout_s=5)
for announced in ({}, {"gpu": "svc0"}):
    backend = HTCondorBackend(NoPilots(), 1, host="127.0.0.1", in_job=SITES["generic"], announced=announced)
    try:
        print(f"announced={announced} service_hosts={backend.service_hosts} driver_memory_mb={backend.driver_memory_mb}"
              f" host_service={'yes' if hasattr(backend, 'host_service') else 'no'}")
        try:
            ServiceSet([small], backend, scope="p").start()
            print("  started (unexpected)")
        except Exception as exc:
            print(f"  {type(exc).__name__}: {str(exc)[:230]}")
            print(f"  legs: {getattr(exc, 'legs', None)}")
    finally:
        backend.close()
