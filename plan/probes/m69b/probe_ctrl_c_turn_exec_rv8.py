"""On a real pool (m68b-minicondor), at ce39e42: frozen row 8's three Ctrl-C forms (`run`, `result`, `close`), each
with a second plan B waiting its turn for the backend's set lock while plan A's server waits for a slot a blocker
holds. B runs `runner.run` on a non-daemon thread, so a wait that never ends keeps the child alive. After SIGINT:
does the child exit, how does B end, and which jobs did the run submit (B's server, pilots)?
Run as submituser with PYTHONPATH=/work/src:/work/tests/frozen/m68a; argv[1] = a scratch dir, argv[2] = form."""

from __future__ import annotations

import dataclasses
import logging
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

POLL_S = 2.0


def served(tag: str, mb: int) -> Any:
    from services_harness import plain_plan

    from graphed_executors.submit import recipes

    spec = recipes.http_server(f"{tag}1")
    assert spec.launch is not None
    spec = dataclasses.replace(spec, timeout_s=120.0, launch=dataclasses.replace(spec.launch, resources={"memory_mb": mb}))
    return dataclasses.replace(plain_plan(1, f"rv8-ctrl-c-{tag}"), services=(spec,))


def child(form: str, log_dir: str) -> None:
    from services_harness import HARNESS_FILE

    from graphed_executors.htcondor_backend import server as server_mod
    from graphed_executors.htcondor_backend.backend import htcondor_runner

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(name)s %(message)s")
    server_mod.POLL_S = POLL_S
    plan_a, plan_b = served("a", 2000), served("b", 512)
    with htcondor_runner(
        n_pilots=1, site="generic", service_hosts=("cluster",), log_dir=log_dir, request_memory_mb=512,
        user_modules=[HARNESS_FILE],
    ) as runner:

        def run_b() -> None:
            time.sleep(4.0)  # plan A's set holds the turn by then
            print("B calls run", flush=True)
            try:
                got = f"value {runner.run(plan_b).value}"
            except BaseException as exc:  # noqa: BLE001
                got = f"{type(exc).__name__}: {exc}"
            print(f"B ended: {got}", flush=True)

        threading.Thread(target=run_b).start()
        if form == "run":
            runner.run(plan_a)
        elif form == "result":
            runner.submit(plan_a).result()
        else:
            runner.submit(plan_a)


def parent(root: Path, form: str) -> None:
    import htcondor2 as htc

    schedd = htc.Schedd()
    t0 = time.monotonic()
    q0 = int(time.time())

    def say(msg: str) -> None:
        print(f"{time.monotonic() - t0:7.1f}s {msg}", flush=True)

    ads = htc.Collector().query(htc.AdType.Startd, projection=["SlotType", "TotalSlotMemory", "Memory"])
    largest = max(int(a.get("TotalSlotMemory", a.get("Memory", 0))) for a in ads if a.get("SlotType") != "Dynamic")
    blocker = int(schedd.submit(htc.Submit({
        "executable": "/bin/sleep", "arguments": "900", "request_memory": str(largest - 256), "request_cpus": "1",
        "JobBatchName": "rv8-blocker"})).cluster())
    while [a["JobStatus"] for a in schedd.query(f"ClusterId == {blocker}", ["JobStatus"])] != [2]:
        time.sleep(1)
    say(f"blocker {blocker} runs ({largest - 256} of {largest} MiB)")
    proc = subprocess.Popen([sys.executable, "-u", __file__, str(root / form), form, "--child"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list[str] = []
    waiting, b_called = threading.Event(), threading.Event()

    def read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if "waits for a slot" in line:
                waiting.set()
            if "B calls run" in line:
                b_called.set()

    threading.Thread(target=read, daemon=True).start()
    try:
        deadline = time.monotonic() + 120
        while not (waiting.is_set() and b_called.is_set()) and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.5)
        time.sleep(3 * POLL_S)  # B is in its turn-wait
        say(f"A waits for a slot={waiting.is_set()}, B called run={b_called.is_set()}; SIGINT")
        sent = time.monotonic()
        proc.send_signal(signal.SIGINT)
        try:
            code: int | None = proc.wait(60)
        except subprocess.TimeoutExpired:
            code = None
        say(f"child exit={code} {time.monotonic() - sent:.1f}s after SIGINT")
        time.sleep(1)
        for line in lines:
            if line.startswith("B ") or "Error" in line or "Interrupt" in line:
                say(f"child: {line.rstrip()[:260]}")
        mine = f"QDate >= {q0} && ClusterId != {blocker}"
        jobs = list(schedd.query(mine, ["ClusterId", "JobBatchName", "JobStatus"])) + list(
            schedd.history(mine, ["ClusterId", "JobBatchName", "JobStatus", "NumJobStarts"], match=20))
        for a in sorted(jobs, key=lambda a: a["ClusterId"]):
            say(f"job {a['ClusterId']} {a.get('JobBatchName')} JobStatus={a.get('JobStatus')} NumJobStarts={a.get('NumJobStarts', 0)}")
        say(f"queued now: {len(list(schedd.query(mine, ['ClusterId'])))}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(30)
        schedd.act(htc.JobAction.Remove, f"ClusterId == {blocker}")


if __name__ == "__main__":
    if sys.argv[3:] == ["--child"]:
        child(sys.argv[2], sys.argv[1])
    else:
        parent(Path(sys.argv[1]), sys.argv[2])
