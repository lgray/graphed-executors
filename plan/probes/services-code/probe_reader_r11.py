# r11 reviewer: N6 closed at the reader? m67 RunHandle.result() (control) vs the plan's one-try reader.
import pickle, subprocess, sys, tempfile, pathlib, textwrap
d = pathlib.Path(tempfile.mkdtemp())
(d / "imageonly.py").write_text("class ImageOnlyError(RuntimeError):\n    pass\n")
sys.path.insert(0, str(d)); from imageonly import ImageOnlyError
(d / "result.pkl").write_bytes(pickle.dumps((False, ImageOnlyError("infer failed"))))
(d / "ok.pkl").write_bytes(pickle.dumps((True, ImageOnlyError("a success payload"))))
sub = textwrap.dedent(f"""
import pickle, pathlib
from graphed_executors.htcondor_backend import driverless as dl
from graphed_executors.htcondor_backend.driverless import RunHandle
RunHandle._located = lambda self: (None, None)
RunHandle._poll = lambda self, s: ("failed", False)
h = RunHandle("generic", "s", 1, {str(d)!r}, 0.0)
try: h.result()
except BaseException as e: print("m67 result():", type(e).__name__, e)
def plan_result(name):  # the plan's reader: one try around the load, raise outside it
    try:
        ok, payload = pickle.loads((pathlib.Path({str(d)!r}) / name).read_bytes())
    except Exception as exc:
        raise RuntimeError(f"result.pkl did not load here ({{type(exc).__name__}}: {{exc}}); see driver.log") from exc
    if not ok: raise payload
    return payload
for n in ("result.pkl", "ok.pkl"):
    try: plan_result(n)
    except BaseException as e: print("plan reader", n, ":", type(e).__name__, e)
""")
r = subprocess.run([sys.executable, "-c", sub], capture_output=True, text=True)
print(r.stdout, r.stderr[-400:])
