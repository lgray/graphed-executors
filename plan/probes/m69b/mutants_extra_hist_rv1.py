"""Mutants run against tests/extra only (m69b + the rewritten m48 witness): each extra test must kill
the mechanism it names without the frozen suite's help. Same driver contract as mutants_hist_rv1.py."""
import os, subprocess, sys
from pathlib import Path
WT = Path(sys.argv[1]); PY = sys.argv[2]
HS, BO = "src/graphed_histogram/histserv.py", "src/graphed_histogram/boost.py"
S, V = "tests/extra/m69b/test_histserv_sizing.py", "tests/extra/m69b/test_histserv_served.py"
MUTANTS = [
  ("size-without-flow", HS, "extent = math.prod(_make_axis(axis).extent for axis in dense_axes)", "extent = math.prod(len(_make_axis(axis)) for axis in dense_axes)", [S+"::test_slots_are_sized_by_flow_extents_with_one_chunk_per_axis_label"]),
  ("axis-mode-one-chunk", HS, "    return _Size(1 if labels is None else len(labels),", "    return _Size(1,", [S+"::test_slots_are_sized_by_flow_extents_with_one_chunk_per_axis_label"]),
  ("refusal-after-placement", HS, "    seen: set[str] = set()\n    for task in plan.tasks:", "    for key, spec, ctx in backing:\n        ctx._pack.place(_size(key, spec, len(plan.tasks)))\n    seen: set[str] = set()\n    for task in plan.tasks:", [S+"::test_a_refused_serve_opens_no_server"]),
  ("services-drop-own", HS, "    services = {s.name: s for s in plan.services} | landed", "    services = dict(landed)", [S+"::test_a_served_plan_keeps_its_own_services_and_declares_the_servers"]),
  ("no-declare", HS, "        session.declare_service(spec)", "        pass", [S+"::test_a_served_plan_keeps_its_own_services_and_declares_the_servers"]),
  ("workers-zero-accepted", HS, "        if workers < 1:", "        if workers < 0:", [S+"::test_a_context_without_workers_is_refused"]),
  ("ports-not-compared", HS, "        return (self.memory_mb, self.workers, self.ports, self.timeout_s)", "        return (self.memory_mb, self.workers, self.timeout_s)", [S+"::test_a_context_differing_only_in_ports_is_refused_naming_the_remedy"]),
  ("setstate-creates", HS, "        self._lock = threading.Lock()\n        self._ids = ids", "        self._lock = threading.Lock()\n        self._ids = None", [V+"::test_an_unpickled_copy_fills_the_histograms_the_driver_created"]),
  ("empty-is-zero-hist", BO, "        return {key: Receipt(spec) if key in backed else zero_of(spec) for key, _ids, spec in self.layout}", "        return {key: zero_of(spec) for key, _ids, spec in self.layout}", [V+"::test_a_served_plan_over_no_partition_resolves_to_empty_histograms"]),
  ("unbound-call-silent", HS, "        if self.endpoints is None or self.handles is None:\n            raise UnboundService(*self._names())", "        if self.endpoints is None or self.handles is None:\n            return self.inner(partition, resources)", [V+"::test_an_unbound_served_process_refuses_its_task_naming_every_server"]),
  ("grpc-refused", HS, 'not in ("tcp", "grpc"):', 'not in ("tcp",):', [V+"::test_a_grpc_endpoint_is_the_plaintext_wire"]),
  ("positions-dedup", BO, "    return {n.node_id: order[compiled.correspondence.node_map[n.node_id][0]] for n in nodes}", "    seen = {}\n    for n in nodes:\n        seen.setdefault(compiled.correspondence.node_map[n.node_id][0], n.node_id)\n    return {n.node_id: (order[compiled.correspondence.node_map[n.node_id][0]] if seen[compiled.correspondence.node_map[n.node_id][0]] == n.node_id else len(order)) for n in nodes}", ["tests/extra/m48/test_review_witnesses.py::test_a_merge_inside_an_unvaried_sibling_sums_both_fills_beside_a_varied_output"]),
]
for name, rel, old, new, tests in MUTANTS:
    path = WT / rel; text = path.read_text()
    assert text.count(old) == 1, (name, text.count(old))
    try:
        path.write_text(text.replace(old, new))
        r = subprocess.run([PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *tests], cwd=WT,
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(WT / "src")})
    finally:
        path.write_text(text)
    last = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [r.stderr[-150:]]
    print(f"{name:26s} {'KILLED' if r.returncode else 'SURVIVED':8s} {last[0][:90]}", flush=True)
print("worktree diff after mutants:", repr(subprocess.run(["git", "diff", "--stat"], cwd=WT, capture_output=True, text=True).stdout))
