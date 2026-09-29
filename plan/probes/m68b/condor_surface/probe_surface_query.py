"""Surface area Q: schedd queries — what a projection returns, history projection/match/order, undefined attributes in
projections and constraints, DAG_* attributes on a non-DAG job.

Run: docker exec -u submituser -w /home/submituser surf-life python3 /probes/condor_surface/probe_surface_query.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import base, fresh, header, hist, htc, rm, say, schedd, submit, wait_gone, wait_status

header("probe_surface_query")
d = fresh("q")
c = submit(base(d, executable="/bin/sleep", arguments="300"))
wait_status(c, (2,), 60)
full = schedd.query("ClusterId == %d" % c)[0]
say("Q1 query() without projection: %d attributes" % len(full.keys()))
for proj in (["JobStatus"], ["JobStatus", "HoldReasonCode", "ExitCode"], ["JobStatus", "DAG_JobsHeld", "NoSuchAttr"]):
    a = schedd.query("ClusterId == %d" % c, proj)[0]
    say("Q2 projection %s -> keys %s" % (proj, sorted(a.keys())))
for cons in ("DAG_JobsHeld > 0", "DAG_JobsHeld =?= 0", "!(DAG_JobsHeld > 0)", "NoSuchAttr == 1 || ClusterId == %d" % c):
    try:
        n = len(schedd.query("(%s) && ClusterId == %d" % (cons, c), ["JobStatus"]))
        say("Q3 constraint %-40r on a non-DAG job matches %d" % (cons, n))
    except Exception as e:
        say("Q3 constraint %r raised %s %s" % (cons, type(e).__name__, e))
rm(c)
wait_gone(c)
for proj in (["JobStatus"], ["JobStatus", "ExitCode", "RemoveReason", "NoSuchAttr"]):
    h = hist(c, proj)
    say("Q4 history projection %s -> keys %s" % (proj, sorted(h[0].keys()) if h else None))
cs = []
for i in range(3):
    cs.append(submit(base(d, executable="/bin/true", output="o%d" % i)))
for x in cs:
    wait_gone(x)
got = list(schedd.history("ClusterId >= %d" % cs[0], ["ClusterId"], match=2))
say("Q5 history(match=2) over clusters %s returns %s (most recent first?)" % (cs, [g.get("ClusterId") for g in got]))
got = list(schedd.history(None, ["ClusterId"], match=-1, since=cs[0]))
say("Q5b history(since=%d) returns %s" % (cs[0], [g.get("ClusterId") for g in got]))
try:
    schedd.history("ClusterId == %d" % cs[0], ["JobStatus"], 1)
    say("Q6 history(constraint, projection, 1) positional match accepted")
except Exception as e:
    say("Q6 positional match raised", type(e).__name__, e)
say("Q-done")
