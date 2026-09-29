"""L7 standalone: does Schedd.act(action, spec, reason=...) set RemoveReason / HoldReason? Run with the pool's own
bindings and with the PyPI wheel CI installs (the plan's test-htcondor job; the wheel authenticates with an IDTOKEN made by
`condor_token_create -identity submituser@$(condor_config_val UID_DOMAIN)` into ~submituser/.condor/tokens.d/):

  docker exec -u submituser -w /home/submituser surf-pool python3 /probes/condor_surface/probe_surface_actreason.py
  docker exec -u submituser -w /home/submituser -e CONDOR_CONFIG=/etc/condor/condor_config surf-pool /opt/wheelvenv/bin/python /probes/condor_surface/probe_surface_actreason.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import base, final, fresh, htc, rm, say, schedd, submit, wait_gone, wait_status

import classad2

say("# bindings", htc.version(), "| interpreter", sys.executable)
d = fresh("actreason")
for label, spec in (("constraint str", lambda c: "ClusterId == %d" % c), ("int cluster", lambda c: c),
                    ("'c.0' str", lambda c: "%d.0" % c), ("ExprTree", lambda c: classad2.ExprTree("ClusterId == %d" % c))):
    c = submit(base(d, executable="/bin/sleep", arguments="300"))
    wait_status(c, (2,), 60)
    schedd.act(htc.JobAction.Remove, spec(c), reason="graphed: via %s" % label)
    wait_gone(c, 60)
    say("L7 act(Remove, %-14s reason=...) -> history" % label, final(c, ("JobStatus", "RemoveReason", "ExitReason")))
c = submit(base(d, executable="/bin/sleep", arguments="300"))
wait_status(c, (2,), 60)
schedd.act(htc.JobAction.Hold, "ClusterId == %d" % c, reason="graphed: hold reason")
a = wait_status(c, (5,), 30, ("JobStatus", "HoldReasonCode", "HoldReason"))
say("L7 act(Hold, reason=...) -> queue", {k: a.get(k) for k in ("JobStatus", "HoldReasonCode", "HoldReason")})
rm(c)
c = submit(base(d, executable="/bin/sleep", arguments="300"))
wait_status(c, (2,), 60)
subprocess.run(["condor_rm", "-reason", "graphed: via condor_rm -reason", str(c)], capture_output=True, text=True)
wait_gone(c, 60)
say("L7 condor_rm -reason (CLI control) -> history", final(c, ("JobStatus", "RemoveReason")))
