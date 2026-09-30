"""m69b-r2: §5.1 "a second context under a used `name` with equal arguments shares the first's servers and packing
state and warns naming it, with other arguments is refused naming both", implemented as written with the name
held for the process (a module-level map), run through the sequences the frozen rows build in one pytest process:
test_histserv_packing's expected placement run after another test's equal context, and its monotonicity sweep.
The packing is §5.1's first-fit over (stored desc, key) against memory_mb; sizes are abstract units.

Run: python3 probe_context_scope_rv2.py > probe_context_scope_rv2.txt
"""
from __future__ import annotations

import warnings

_USED: dict[str, tuple[tuple, list]] = {}


class Context:
    def __init__(self, *, memory_mb: int, workers: int, name: str = "histserv") -> None:
        args = (memory_mb, workers)
        if name in _USED:
            first, servers = _USED[name]
            if first != args:
                raise ValueError(f"context name {name!r} is used with {first}, not {args}")
            warnings.warn(f"a second context named {name!r} shares its servers", stacklevel=2)
        else:
            _USED[name] = (args, [])
        self.memory_mb, self.name, self.servers = memory_mb, name, _USED[name][1]

    def serve(self, slots: dict[str, int]) -> dict[str, str]:
        placed = {}
        for key, size in sorted(slots.items(), key=lambda kv: (-kv[1], kv[0])):
            for i, load in enumerate(self.servers):
                if load + size <= self.memory_mb:
                    self.servers[i] += size
                    break
            else:
                self.servers.append(size)
                i = len(self.servers) - 1
            placed[key] = f"{self.name}-{i}"
        return placed


warnings.simplefilter("ignore")
SLOTS = {"a": 60, "b": 30, "c": 20}
alone = Context(memory_mb=100, workers=1).serve(SLOTS)
print(f"placement test alone:               {alone}")
_USED.clear()
Context(memory_mb=100, workers=1).serve({"other_test": 50})  # an earlier test in the same process
after = Context(memory_mb=100, workers=1).serve(SLOTS)
print(f"placement test after an equal one:  {after}  (same as alone: {after == alone})")
_USED.clear()
for workers in (1, 2):
    try:
        Context(memory_mb=100, workers=workers)
        print(f"monotonicity sweep workers={workers}: built")
    except ValueError as e:
        print(f"monotonicity sweep workers={workers}: ValueError: {e}")
