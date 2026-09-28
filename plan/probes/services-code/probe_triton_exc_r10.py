# r10 reviewer: does tritonclient's InferenceServerException pass the plan's driver-side round trip?
import pickle
from tritonclient.utils import InferenceServerException
for e in (InferenceServerException("model not ready", "StatusCode.UNAVAILABLE", "d"),
          InferenceServerException(msg="kw", status="s")):
    try:
        back = pickle.loads(pickle.dumps(e)); print("round-trips:", type(back).__name__, str(back))
    except Exception as x:
        print("round trip fails:", type(x).__name__, x)
