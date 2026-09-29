"""Surface area N: networking and identity from jobs — the machine ad's Machine vs the job's own hostname, whether it
resolves in the job, one job dialling another's port by Machine, condor_ssh_to_job, a job submitting to the pool.

Run: docker exec -u submituser -w /home/submituser surf-life python3 /probes/condor_surface/probe_surface_network.py
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from surface_lib import base, final, fresh, header, q, read, rm, say, schedd, script, short, submit, wait, wait_gone, wait_status, write

header("probe_surface_network")
d = fresh("n")
IDENT = r'''
import os, socket
ad = os.environ.get("_CONDOR_MACHINE_AD")
m = None
for line in open(ad):
    k, _, v = line.partition("=")
    if k.strip() == "Machine": m = v.strip().strip('"')
print("Machine=%s gethostname=%s getfqdn=%s" % (m, socket.gethostname(), socket.getfqdn()))
try: print("Machine resolves to", socket.gethostbyname(m))
except OSError as e: print("Machine does not resolve:", e)
'''
write(os.path.join(d, "ident.py"), IDENT)
script(os.path.join(d, "ident.sh"), "exec python3 ident.py\n")
c = submit(base(d, executable=os.path.join(d, "ident.sh"), transfer_input_files=os.path.join(d, "ident.py"), output="ident.out"))
wait_gone(c)
say("N1", read(os.path.join(d, "ident.out")).replace("\n", " | "))

SERVER = r'''
import http.server, os, socket, sys
port = int(sys.argv[1])
srv = http.server.HTTPServer(("0.0.0.0", port), http.server.SimpleHTTPRequestHandler)
open(sys.argv[2], "w").write("listening %d\n" % port)
srv.serve_forever()
'''
CLIENT = r'''
import os, sys, urllib.request
m = [l.split("=", 1)[1].strip().strip('"') for l in open(os.environ["_CONDOR_MACHINE_AD"]) if l.split("=")[0].strip() == "Machine"][0]
for host in (m, "127.0.0.1"):
    try:
        r = urllib.request.urlopen("http://%s:%s/" % (host, sys.argv[1]), timeout=5)
        print("GET http://%s:%s/ -> %s" % (host, sys.argv[1], r.status))
    except Exception as e:
        print("GET http://%s:%s/ -> %s" % (host, sys.argv[1], e))
'''
write(os.path.join(d, "server.py"), SERVER)
write(os.path.join(d, "client.py"), CLIENT)
flag = os.path.join(d, "server-listening")
script(os.path.join(d, "server.sh"), "exec python3 server.py 10050 %s\n" % flag)
script(os.path.join(d, "client.sh"), "exec python3 client.py 10050\n")
cs = submit(base(d, executable=os.path.join(d, "server.sh"), transfer_input_files=os.path.join(d, "server.py"), output="server.out"))
wait(lambda: os.path.exists(flag), 90)
cc = submit(base(d, executable=os.path.join(d, "client.sh"), transfer_input_files=os.path.join(d, "client.py"), output="client.out"))
wait_gone(cc)
say("N2 job B dialling job A's port:", read(os.path.join(d, "client.out")).replace("\n", " | "))

# N3 condor_ssh_to_job into the running server job
p = subprocess.run(["condor_ssh_to_job", "%d.0" % cs, "pwd; ls -A | tr '\\n' ' '; echo; echo KRB5CCNAME=$KRB5CCNAME"], capture_output=True, text=True, timeout=120)
say("N3 condor_ssh_to_job rc=%d stdout=%r stderr=%r" % (p.returncode, p.stdout.strip()[:300], short(p.stderr, 200)))
rm(cs)

# N4 a job that submits a job to the pool's schedd (m67 self-submit, located by name through the collector)
INNER = r'''
import htcondor2 as htc
coll = htc.param["COLLECTOR_HOST"]
name = htc.Collector(coll).locate(htc.DaemonType.Schedd)["Name"]
s = htc.Schedd(htc.Collector(coll).locate(htc.DaemonType.Schedd, name))
r = s.submit(htc.Submit({"executable": "/bin/true", "initialdir": "%s", "log": "inner.log", "request_memory": "64",
                          "should_transfer_files": "YES"}))
print("inner cluster", r.cluster(), "via", coll, name)
''' % d
write(os.path.join(d, "inner.py"), INNER)
script(os.path.join(d, "outer.sh"), "exec python3 inner.py\n")
c = submit(base(d, executable=os.path.join(d, "outer.sh"), transfer_input_files=os.path.join(d, "inner.py"), output="outer.out", error="outer.err"))
wait_gone(c)
say("N4 submit from inside a job:", final(c, ("JobStatus", "ExitCode")), read(os.path.join(d, "outer.out")).strip(), short(read(os.path.join(d, "outer.err")), 200))
say("N-done")
