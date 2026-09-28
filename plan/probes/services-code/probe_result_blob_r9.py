# r9 planner: (a) stdlib exception pickling when args == constructor args; (b) a round-tripping _result_blob
import pickle
from graphed_executors.htcondor_backend import driver


class Natural(RuntimeError):  # args != constructor args
    def __init__(self, name, endpoint, worker, reason):
        super().__init__(f"{name}: {reason}")
        self.name, self.endpoint, self.worker, self.reason = name, endpoint, worker, reason


class ArgsForm(RuntimeError):  # args == constructor args; __str__ names the reason
    def __init__(self, name, endpoint, worker, reason):
        super().__init__(name, endpoint, worker, reason)
        self.name, self.endpoint, self.worker, self.reason = name, endpoint, worker, reason

    def __str__(self):
        return f"service {self.name!r} at {self.endpoint} unreachable from {self.worker}: {self.reason}"


class Unavailable(RuntimeError):
    def __init__(self, name, legs):
        super().__init__(name, dict(legs))
        self.name, self.legs = name, dict(legs)

    def __str__(self):
        return f"service {self.name!r} unavailable: " + "; ".join(f"{k}: {v}" for k, v in self.legs.items())


def round_trip_blob(ok, payload):  # the proposed _result_blob
    try:
        blob = pickle.dumps((ok, payload))
        pickle.loads(blob)
        return blob
    except Exception as exc:
        return pickle.dumps((False, RuntimeError(f"{type(payload).__name__} did not pickle ({exc}): {payload}")))


cases = [Natural("t", "grpc://h:1", "w1", "refused"), ArgsForm("t", "grpc://h:1", "w1", "refused"),
         Unavailable("t", {"user": "none given", "site": "none", "managed": "no launch"})]
for blob_fn in (driver._result_blob, round_trip_blob):
    for e in cases:
        try:
            ok, err = pickle.loads(blob_fn(False, e))
            print(f"{blob_fn.__name__:16} {type(e).__name__:11} -> {type(err).__name__} "
                  f"fields={getattr(err, 'reason', getattr(err, 'legs', None))!r} str={str(err)!r}")
        except Exception as exc:
            print(f"{blob_fn.__name__:16} {type(e).__name__:11} -> loads raises {type(exc).__name__}: {exc}")
