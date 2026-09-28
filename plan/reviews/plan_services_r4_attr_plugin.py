"""pytest -p plugin: bind host_service/release_service as plan-services D10 describes, count bindings."""
import functools

from graphed_executors.dask_backend.backend import DaskBackend
from graphed_executors.htcondor_backend.backend import HTCondorBackend
from graphed_executors.parsl_backend.backend import ParslBackend

BOUND: dict[str, int] = {}


def _host(spec):  # never called by the frozen suites
    raise AssertionError("host_service called")


def _release(name):
    raise AssertionError("release_service called")


def _wrap(cls, pred):
    orig = cls.__init__

    @functools.wraps(orig)
    def init(self, *a, **k):
        orig(self, *a, **k)
        if pred(self):
            self.host_service, self.release_service = _host, _release
            BOUND[cls.__name__] = BOUND.get(cls.__name__, 0) + 1

    cls.__init__ = init


_wrap(HTCondorBackend, lambda s: True)  # worst case: every condor instance hosts
_wrap(ParslBackend, lambda s: s._is_htex)
_wrap(DaskBackend, lambda s: True)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"R4_BOUND {sorted(BOUND.items())}")
