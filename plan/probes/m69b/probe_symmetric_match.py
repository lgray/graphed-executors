"""Does a queued job's own ad, symmetricMatch-ed against the pool's Machine ads with partitionable totals copied
into Memory/Cpus/GPUs, answer "could this job ever run here" (m68b-minicondor:local, htcondor2 25.13.2)?

  docker run -d --rm --name m69b-match-probe -v "$PWD:/p" m68b-minicondor:local
  docker exec m69b-match-probe sh -c 'echo "UPDATE_INTERVAL = 5" > /etc/condor/config.d/99-m69b.conf && condor_reconfig'
  docker exec -u submituser -w /tmp m69b-match-probe /opt/venv/bin/python /p/probe_symmetric_match.py
"""

import time

import classad2
import htcondor2 as htc

schedd = htc.Schedd()
coll = htc.Collector()


def machines() -> list:
    return [ad for ad in coll.query(constraint='MyType == "Machine"') if ad.get("SlotType") != "Dynamic"]


def substituted(ad):
    m = classad2.ClassAd(str(ad))  # a copy: the collector's ad stays as queried
    if m.get("PartitionableSlot"):
        for total, free in (("TotalSlotMemory", "Memory"), ("TotalSlotCpus", "Cpus"), ("TotalSlotGPUs", "GPUs")):
            if total in m:
                m[free] = m[total]
    return m


def submit(batch: str, **keys: str) -> int:
    desc = {"executable": "/bin/sleep", "arguments": "300", "request_cpus": "1", "JobBatchName": batch,
            "log": f"/tmp/{batch}.log", **keys}
    return int(schedd.submit(htc.Submit(desc)).cluster())


def job_ad(cluster: int):
    (ad,) = schedd.query(constraint=f"ClusterId == {cluster}")
    return ad


def verdict(label: str, cluster: int, ads: list) -> None:
    job = job_ad(cluster)
    raw = [job.symmetricMatch(ad) for ad in ads]
    sub = [job.symmetricMatch(substituted(ad)) for ad in ads]
    print(f"{label}: Requirements = {job.lookup('Requirements')}")
    print(f"    raw ads match {raw}; substituted ads match {sub}")


def status(cluster: int):
    ads = schedd.query(constraint=f"ClusterId == {cluster}", projection=["JobStatus"])
    return int(ads[0]["JobStatus"]) if ads else None


def main() -> None:
    ads = machines()
    total = max(int(ad.get("TotalSlotMemory", ad.get("Memory", 0))) for ad in ads)
    print(f"{len(ads)} non-dynamic Machine ads; largest slot memory {total} MiB; GPUs {[ad.get('TotalSlotGPUs') for ad in ads]}")

    cases = {
        "fit 1024 MiB": submit("m69b-fit", request_memory="1024"),
        f"oversize {total + 1} MiB": submit("m69b-oversize", request_memory=str(total + 1)),
        "request_gpus=1": submit("m69b-gpu", request_memory="1024", request_gpus="1"),
        "extra requirements OpSysMajorVer == 99": submit(
            "m69b-extra", request_memory="1024", requirements="(TARGET.OpSysMajorVer == 99)"
        ),
    }
    for label, cluster in cases.items():
        verdict(label, cluster, ads)
    oversize = cases[f"oversize {total + 1} MiB"]
    for cluster in cases.values():
        schedd.act(htc.JobAction.Remove, f"ClusterId == {cluster}")
    time.sleep(3)
    (hist,) = list(schedd.history(f"ClusterId == {oversize}", ["JobStatus", "NumJobStarts", "JobCurrentStartDate"], match=1))
    print(f"removed oversize job in history: {dict(hist)} (JobCurrentStartDate present: {'JobCurrentStartDate' in hist})")

    blocker = submit("m69b-blocker", request_memory=str(total - 1024))
    t0 = time.monotonic()
    while status(blocker) != 2 and time.monotonic() - t0 < 60:
        time.sleep(0.5)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        busy = machines()
        if all(int(ad.get("Memory", 0)) < total for ad in busy if ad.get("PartitionableSlot")):
            break
        time.sleep(2)
    print(f"busy pool: partitionable Memory now {[ad.get('Memory') for ad in busy]} of {total}")
    waiting = submit("m69b-behind", request_memory="4096")
    verdict("4096 MiB behind the blocker", waiting, busy)
    print(f"    behind-the-blocker JobStatus after the check: {status(waiting)}")
    for cluster in (blocker, waiting):
        schedd.act(htc.JobAction.Remove, f"ClusterId == {cluster}")


if __name__ == "__main__":
    main()
