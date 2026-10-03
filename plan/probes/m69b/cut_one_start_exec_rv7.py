"""The H-a cut, prototyped: one plan's services start at a time (ServiceSet resolve phases serialized per backend),
so no set is admitted beside another set's servers that are still starting. argv[1] = backend.py to patch in place."""

import sys

p = sys.argv[1]
s = open(p).read()
old_init = "        self._starting = 0  # plans whose services are starting (ServiceSet resolve phases)\n"
new_init = old_init + "        self._start_turn = threading.Lock()  # one plan's services start at a time\n"
old_head = """        with self._pilots_lock:
            self._starting += 1
        try:
            yield
        finally:
            with self._pilots_lock:
                self._starting -= 1
                if not self._starting and (self._wanted or self._held):
                    self._wanted = False
                    release_quietly("the pilots", self._move_pilots)
"""
new_head = """        while not self._start_turn.acquire(timeout=1.0):
            if self._closing.is_set():
                raise RuntimeError("the runner closed before this plan's services started")
        try:
            with self._pilots_lock:
                self._starting += 1
            try:
                yield
            finally:
                with self._pilots_lock:
                    self._starting -= 1
                    if not self._starting and (self._wanted or self._held):
                        self._wanted = False
                        release_quietly("the pilots", self._move_pilots)
        finally:
            self._start_turn.release()
"""
assert s.count(old_init) == 1 and s.count(old_head) == 1
open(p, "w").write(s.replace(old_init, new_init).replace(old_head, new_head))
print("patched", p)
