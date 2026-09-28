# r7 m68a premise: inside a driverless driver job with pilots="local", the HTCondorBackend's profile is
# SITES["generic"] whatever run.json.site says (LocalPilots carries no profile).
import sys
from graphed_executors.htcondor_backend.backend import HTCondorBackend
from graphed_executors.htcondor_backend.launch import LocalPilots, CondorPilots
from graphed_executors.htcondor_backend.sites import SITES
for site in ("lpc", "lxplus"):
    prof = SITES[site]
    b = HTCondorBackend(LocalPilots(python=sys.executable), 1, host="127.0.0.1", port_range=prof.worker_ports)
    print(f"local pilots, run.site={site}: backend profile resolved as",
          getattr(b.launcher, "profile", SITES["generic"]).name, "| hasattr(LocalPilots,'profile') =", hasattr(b.launcher, "profile"))
    b._server.stop() if hasattr(b._server, "stop") else None
# control: a launcher that carries the profile resolves to it
c = CondorPilots(SITES["lpc"], image="x", request_memory_mb=1, log_dir="/tmp")
print("control CondorPilots(lpc).profile =", c.profile.name)
