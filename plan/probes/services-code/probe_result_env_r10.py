# r10 reviewer: a blob that round-trips in the driver's env but not in the submitter's
import pickle, subprocess, sys, tempfile, pathlib, importlib.util

def round_trip_blob(ok, payload):  # the plan's r10 _result_blob
    try:
        blob = pickle.dumps((ok, payload)); pickle.loads(blob); return blob
    except Exception as exc:
        return pickle.dumps((False, RuntimeError(f"{type(payload).__name__} did not pickle ({exc}): {payload}")))

d = pathlib.Path(tempfile.mkdtemp())
(d / "imageonly.py").write_text("class ImageOnlyError(RuntimeError):\n    pass\n")
sys.path.insert(0, str(d))  # the driver job's env (an image package, or the job dir)
from imageonly import ImageOnlyError
blob = round_trip_blob(False, ImageOnlyError("infer failed"))
print("driver-side round trip:", type(pickle.loads(blob)[1]).__name__)
out = d / "result.pkl"; out.write_bytes(blob)
r = subprocess.run([sys.executable, "-c", f"import pickle; pickle.loads(open({str(out)!r},'rb').read())"],
                   capture_output=True, text=True)  # the submitter's env: no imageonly
print("submitter loads rc", r.returncode, "|", r.stderr.strip().splitlines()[-1])
print("tritonclient installed here:", importlib.util.find_spec("tritonclient") is not None)
