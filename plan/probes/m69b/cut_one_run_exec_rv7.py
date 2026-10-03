"""The H-a cut, prototyped: an HTCondorRunner runs one plan at a time (its `run`, which `submit`'s driver thread also
calls, takes a runner lock), as PlanQueue already does for submitted plans. argv[1] = backend.py to patch in place."""

import sys

p = sys.argv[1]
s = open(p).read()
old_init = "        self._min_pilots = backend.min_pilots = min_pilots\n"
new_init = old_init + "        self._one_run = threading.Lock()  # plans of one runner never overlap: none waits on another's holds\n"
old_run = """        _require_plan_importable(plan, ("process", "combine"))
        return super().run(plan)
"""
new_run = """        _require_plan_importable(plan, ("process", "combine"))
        with self._one_run:
            return super().run(plan)
"""
assert s.count(old_init) == 1 and s.count(old_run) == 1
open(p, "w").write(s.replace(old_init, new_init).replace(old_run, new_run))
print("patched", p)
