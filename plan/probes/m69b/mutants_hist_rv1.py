"""Mutation legs for the m69b histserv backend, run in the reviewer's own worktree (argv[1]).

Each mutant replaces one exact snippet (asserted to occur once), runs the named tests, and restores
the file in a finally. A mutant is KILLED when pytest exits non-zero. The worktree's diff must be
empty at the end.
"""
import subprocess, sys
from pathlib import Path

WT = Path(sys.argv[1]); PY = sys.argv[2]; ONLY = set(sys.argv[3:])
HS, BO = "src/graphed_histogram/histserv.py", "src/graphed_histogram/boost.py"
F = "tests/frozen/m69b/"; X = "tests/extra/m69b/"
MUTANTS = [
  ("ffd-ascending", HS, "key=lambda s: (-s[3].stored, str(s[0]))", "key=lambda s: (s[3].stored, str(s[0]))", [F+"test_histserv_packing.py"]),
  ("ffd-insertion-order", HS, "sorted(sized, key=lambda s: (-s[3].stored, str(s[0])))", "sized", [F+"test_histserv_packing.py"]),
  ("place-largest-size", HS, "server = _Server(fits[0], False, [size])", "server = _Server(fits[-1], False, [size])", [F+"test_histserv_packing.py"]),
  ("oversize-refused", HS, "if fits else _Server(math.ceil(alone / MiB), True, [size])", "if fits else (_ for _ in ()).throw(ValueError('too big'))", [F+"test_histserv_packing.py", F+"test_histserv_fill_path.py"]),
  ("oversize-shared", HS, "if not server.alone and _predict", "if _predict", [F+"test_histserv_packing.py"]),
  ("no-first-fit-reuse", HS, "        for i, server in enumerate(self.servers):\n            if not server.alone", "        for i, server in enumerate([]):\n            if not server.alone", [F+"test_histserv_packing.py"]),
  ("model-drop-task-term", HS, "_PER_HIST + _PER_TASK * s.tasks +", "_PER_HIST +", [F+"test_histserv_packing.py", X+"test_histserv_sizing.py"]),
  ("model-drop-conn-term", HS, " + _PER_CONN * workers\n", "\n", [F+"test_histserv_packing.py"]),
  ("model-chunks-not-plus-one", HS, "(s.chunks + 1) * s.dense", "s.chunks * s.dense", [F+"test_histserv_packing.py", X+"test_histserv_sizing.py"]),
  ("size-without-flow", HS, "extent = math.prod(_make_axis(axis).extent for axis in dense_axes)", "extent = math.prod(len(_make_axis(axis)) for axis in dense_axes)", [F+"test_histserv_packing.py", X+"test_histserv_sizing.py"]),
  ("ceiling-off-by-one", HS, "if size.stored + _ENVELOPE > CEILING:", "if size.stored + _ENVELOPE >= CEILING:", [F+"test_histserv_packing.py"]),
  ("equal-context-fresh-pack", HS, "        self._pack = held\n", "        self._pack = pack\n", [F+"test_histserv_packing.py"]),
  ("different-args-shared", HS, "            if held.args() != pack.args():", "            if False:", [F+"test_histserv_packing.py", X+"test_histserv_sizing.py"]),
  ("equal-no-warning", HS, "            warnings.warn(\n", "            (lambda *a, **k: None)(\n", [F+"test_histserv_packing.py"]),
  ("services-unsorted", HS, "services=tuple(services[n] for n in sorted(services))", "services=tuple(services.values())", [F+"test_histserv_packing.py", X+"test_histserv_sizing.py"]),
  ("unique-id-random", HS, "token = _SCOPE.set((str(partition), homes))", "token = _SCOPE.set((__import__('uuid').uuid4().hex, homes))", [F+"test_histserv_retries.py"]),
  ("already-exists-raises", HS, '        if err.code != "ALREADY_EXISTS":\n            raise', "        raise", [F+"test_histserv_retries.py"]),
  ("resolve-keeps-copies", BO, "h.snapshot(delete=True)", "h.snapshot(delete=False)", [F+"test_histserv_fill_path.py"]),
  ("unpack-deletes", BO, "held.snapshot()", "held.snapshot(delete=True)", [F+"test_histserv_fill_path.py"]),
  ("error-formatted-args", HS, "        super().__init__(endpoint, code, details)\n", "        super().__init__(f'{endpoint} {code} {details}')\n", [F+"test_histserv_retries.py"]),
  ("eager-histserv-import", HS, "import boost_histogram as bh\nimport numpy as np\n", "import boost_histogram as bh\nimport numpy as np\nimport histserv as _eager  # noqa\n", [F+"test_histserv_lazy_init.py", F+"test_histserv_surface.py"]),
  ("worker-creates", HS, "    def __getstate__(self) -> dict[SlotKey, str] | None:\n        return self._ids", "    def __getstate__(self) -> dict[SlotKey, str] | None:\n        return None", [F+"test_histserv_lazy_init.py", X+"test_histserv_served.py"]),
  ("create-at-bind", HS, "        return replace(self, inner=inner, endpoints=bound, handles=_Handles())", "        out = replace(self, inner=inner, endpoints=bound, handles=_Handles())\n        out.handles.ids(bound, self.slots)\n        return out", [F+"test_histserv_lazy_init.py"]),
  ("no-pickle-create", HS, "        if self.endpoints is not None and self.handles is not None:\n            self.handles.ids(self.endpoints, self.slots)\n", "", [F+"test_histserv_lazy_init.py", X+"test_histserv_served.py"]),
  ("bind-no-merge", HS, "merged = {**(self.endpoints or {}), **endpoints}", "merged = dict(endpoints)", [F+"test_histserv_lazy_init.py", F+"test_histserv_fill_path.py"]),
  ("receipt-adds-anything", HS, "        raise GraphedError(\n            f\"receipts of two histserv", "        return self\n        raise GraphedError(\n            f\"receipts of two histserv", [F+"test_histserv_retries.py"]),
  ("positions-dedup", BO, "    return {n.node_id: order[compiled.correspondence.node_map[n.node_id][0]] for n in nodes}", "    seen = {}\n    for n in nodes:\n        seen.setdefault(compiled.correspondence.node_map[n.node_id][0], n.node_id)\n    return {n.node_id: (order[compiled.correspondence.node_map[n.node_id][0]] if seen[compiled.correspondence.node_map[n.node_id][0]] == n.node_id else len(order)) for n in nodes}", ["tests/frozen/m48", "tests/frozen/m49", F+"test_pieces_composition.py"]),
  ("second-firing-records-first", BO, "        if self.reduce.positions:\n            raise GraphedError(\n                \"these pieces already fed", "        first = not self.reduce.positions\n        self.reduce.positions = _positions(compiled, self.fill_nodes)\n        if not first:\n            raise GraphedError(\n                \"these pieces already fed", [F+"test_pieces_composition.py"]),
  ("tls-allowed", HS, 'not in ("tcp", "grpc"):', 'not in ("tcp", "grpc", "grpcs", "https", "http"):', [F+"test_histserv_fill_path.py"]),
  ("handles-no-lock", HS, "        with self._lock:\n            if self._ids is None:", "        if True:\n            if self._ids is None:", [X+"test_histserv_served.py::test_concurrent_first_calls_create_each_histogram_once"]),
]
results = []
for name, rel, old, new, tests in MUTANTS:
    if ONLY and name not in ONLY:
        continue
    path = WT / rel; text = path.read_text()
    assert text.count(old) == 1, (name, text.count(old))
    try:
        path.write_text(text.replace(old, new))
        r = subprocess.run([PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *tests],
                           cwd=WT, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(WT / "src")})
    finally:
        path.write_text(text)
    last = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [r.stderr[-200:]]
    first_fail = next((l for l in r.stdout.splitlines() if l.startswith("FAILED") or l.startswith("ERROR")), "")
    results.append((name, "KILLED" if r.returncode else "SURVIVED", last[0][:110], first_fail[:200]))
    print(f"{name:28s} {results[-1][1]:8s} {last[0][:100]} | {first_fail[:160]}", flush=True)
diff = subprocess.run(["git", "diff", "--stat"], cwd=WT, capture_output=True, text=True).stdout
print("worktree diff after mutants:", repr(diff))
