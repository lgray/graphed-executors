# r8 m68a premises, against m67 (386d65d), built through driver._runner (the construction the plan's in_job cut lands in):
# L: pilots="local", no bindings, synthetic machine ad -> launcher profile, server host, and the pilot-side identity.
# C: pilots="condor" on an lxplus-shaped row with fake bindings -> constructible on any OS; the attached values in_job replaces.
import dataclasses, io, os, sys, tempfile
from pathlib import Path

sys.modules["htcondor2"] = None  # any bindings import now raises
from graphed_executors.htcondor_backend import driver, launch
from graphed_executors.htcondor_backend.sites import SITES

tmp = Path(tempfile.mkdtemp())
ad = tmp / "machine.ad"
ad.write_text('Machine = "slot-host.example"\nCpus = 4\n')
os.environ["_CONDOR_MACHINE_AD"] = str(ad)
try:
    launch._htcondor()
    print("control: bindings import did NOT raise")
except ImportError as exc:
    print("control: launch._htcondor() raises ImportError:", str(exc).split(":")[0])

base = {"n_pilots": 1, "min_pilots": 1, "retries": 1, "max_in_flight": 1}
for site in ("lpc", "lxplus"):
    r = driver._runner({**base, "site": site, "pilots": "local"}, tmp, io.StringIO())
    b = r.backend
    b.wait_for_pilots(1, timeout=60)
    pilot_id = b.submit(driver.machine_host, key=f"id-{site}").result(timeout=60)
    print(f"L site={site}: launcher profile={getattr(b.launcher, 'profile', SITES['generic']).name}"
          f" server={b._server.url} driver machine_host()={driver.machine_host()} pilot machine_host()={pilot_id}"
          f" attached service_hosts of run.site={SITES[site].service_hosts}")
    r.close()


class _Res:
    def cluster(self): return 1


class _Schedd:
    def submit(self, desc, count=0, spool=False): return _Res()
    def spool(self, res): pass
    def query(self, **kw): return []
    def act(self, *a, **kw): pass
    def retrieve(self, *a): pass


class _Coll:
    def locate(self, dt, name=None): return {"Name": name}


class FakeHT:
    class DaemonType: Schedd = "Schedd"
    class JobAction: Remove = "Remove"
    param = {"FULL_HOSTNAME": "login-or-container.example"}
    def Collector(self, pool=None): return _Coll()
    def Schedd(self, loc=None): return _Schedd()
    def Submit(self, d=None): return dict(d or {})


launch._htcondor = lambda: FakeHT()
lx = dataclasses.replace(SITES["lxplus"], name="r8-lx", ship_env=False, spool=False)
SITES["r8-lx"] = lx  # type: ignore[index]
run = {**base, "site": "r8-lx", "pilots": "condor", "image": "x.sif", "request_memory_mb": 1,
       "log_dir": str(tmp / "logs"), "user_modules": [], "schedd_locate": ["pool", "schedd"]}
r = driver._runner(run, tmp, io.StringIO())
b = r.backend
print(f"C site=r8-lx: launcher profile={b.launcher.profile.name} server={b._server.url}"
      f" attached service_hosts={b.launcher.profile.service_hosts} service_ports={b.launcher.profile.service_ports}"
      f" worker_ports={b.launcher.profile.worker_ports} FULL_HOSTNAME={FakeHT.param['FULL_HOSTNAME']}"
      f" machine_host()={driver.machine_host()}")
b._server.close(); b._server.shutdown()
