# r8 N4 premises against m67 (386d65d): which exceptions raised inside runner.run reach _exit_code, and what it maps them to.
# F: the m67 extra 'fail' plan (process raises ValueError) -> type of the error in result.pkl + exit code.
# S: a non-StageError raised inside runner.run (stand-in for ServiceUnavailable) -> exit code today.
import json, pickle, sys, tempfile
from pathlib import Path
from graphed.core.execution import Partition, Plan, Task
from graphed.debug import StageError
from graphed_executors.htcondor_backend import driver

MOD = "def fail(partition, resources):\n    raise ValueError('negative pt')\ndef concat(a, b):\n    return a + b\ndef empty():\n    return ''\n"
tmp = Path(tempfile.mkdtemp()); (tmp / "r8exit.py").write_text(MOD); sys.path.insert(0, str(tmp))
m = __import__("r8exit")
parts = [Partition(f"mem://r8exit/{i}", "", i, i + 1) for i in range(2)]
plan = Plan(process=m.fail, combine=m.concat, empty=m.empty, tasks=tuple(Task(i, p) for i, p in enumerate(parts)))
(tmp / "plan.pkl").write_bytes(pickle.dumps(plan))
(tmp / "run.json").write_text(json.dumps({"pilots": "local", "site": "generic", "n_pilots": 1, "min_pilots": 1, "retries": 0, "max_in_flight": 1}))
code = driver.main([str(tmp)])
ok, err = pickle.loads((tmp / "result.pkl").read_bytes())
print(f"F exit={code} type={type(err).__name__} is_StageError={isinstance(err, StageError)} cause_type={getattr(err, 'cause_type', None)}")

class ServiceUnavailable(RuntimeError): pass
print(f"S exit(_exit_code(ServiceUnavailable))={driver._exit_code(ServiceUnavailable('x'))}"
      f" proposed={3 if isinstance(ServiceUnavailable('x'), StageError) else 1}")
