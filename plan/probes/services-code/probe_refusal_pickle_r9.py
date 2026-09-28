# r9: do the plan's refusal signatures survive driver._result_blob -> driverless-style pickle.loads (result.pkl)?
import pickle
from graphed_executors.htcondor_backend import driver


class ServiceUnreachable(RuntimeError):  # the natural form of ServiceUnreachable(name, endpoint, worker, reason)
    def __init__(self, name, endpoint, worker, reason):
        super().__init__(f"{name} at {endpoint} unreachable from {worker}: {reason}")
        self.name, self.endpoint, self.worker, self.reason = name, endpoint, worker, reason


class Reduced(ServiceUnreachable):  # StageError's __reduce__ idiom
    def __reduce__(self):
        return (self.__class__.__new__, (self.__class__,), self.__dict__.copy())

    def __setstate__(self, state):
        self.__dict__.update(state)


for cls in (ServiceUnreachable, Reduced):
    blob = driver._result_blob(False, cls("triton", "grpc://h:1", "w1", "refused"))
    try:
        ok, err = pickle.loads(blob)
        print(f"{cls.__name__}: loads ok type={type(err).__name__} reason={err.reason!r} str={str(err)!r}")
    except Exception as exc:
        print(f"{cls.__name__}: dumps ok, loads raises {type(exc).__name__}: {exc}")
