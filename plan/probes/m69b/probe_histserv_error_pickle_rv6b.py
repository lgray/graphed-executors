"""r6-B: what "a HistservError ... equal after a pickle round trip" can mean for an Exception subclass.
Run: python3 probe_histserv_error_pickle_rv6b.py"""
import pickle


class Positional(RuntimeError):  # fields passed through to Exception.args
    def __init__(self, endpoint: str, code: str, details: str) -> None:
        super().__init__(endpoint, code, details)
        self.endpoint, self.code, self.details = endpoint, code, details

    def __str__(self) -> str:
        return f"histserv at {self.endpoint}: {self.code} {self.details}"


class Formatted(RuntimeError):  # the common shape: one formatted message to super()
    def __init__(self, endpoint: str, code: str, details: str) -> None:
        super().__init__(f"histserv at {endpoint}: {code} {details}")
        self.endpoint, self.code, self.details = endpoint, code, details


for cls in (Positional, Formatted):
    e = cls("tcp://127.0.0.1:10000", "UNAVAILABLE", "failed to connect")
    try:
        r = pickle.loads(pickle.dumps(e))
        print(f"{cls.__name__}: round trip ok; r == e: {r == e}; same type+str: {type(r) is type(e) and str(r) == str(e)}")
    except Exception as exc:
        print(f"{cls.__name__}: round trip FAILS: {type(exc).__name__}: {exc}")
