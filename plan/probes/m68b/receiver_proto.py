"""Stand-in for the task server's ``/announce`` route (stdlib, python3.9), used by the m68b pool probes.

    python3 receiver_proto.py <secret file (hex)> <lo> <hi> <record file> [<url file>]

Binds the first free port of lo..hi (as ``server._bind`` does), writes its url to <url file> when given
(DAG mode: secret first, then the url, each by atomic rename), and appends each announce to <record file>
as JSON: 403 unsigned/wrong-signed before any parse, 400 unless the body is exactly three fields
``key host:port identity``.
"""

import hashlib
import hmac
import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

secret_hex = open(sys.argv[1]).read().strip()
lo, hi, record = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
url_file = sys.argv[5] if len(sys.argv) > 5 else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sig = self.headers.get("X-Graphed-Sig", "").encode("latin-1")
        want = hmac.new(bytes.fromhex(secret_hex), body, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(sig, want):
            self.send_response(403), self.end_headers()
            return
        fields = body.decode("utf-8", "replace").split()
        ok = self.path == "/announce" and len(fields) == 3 and fields[1].rpartition(":")[2].isdigit()
        self.send_response(200 if ok else 400), self.end_headers()
        with open(record, "a") as f:
            f.write(json.dumps({"path": self.path, "fields": fields, "ok": ok, "port": port}) + "\n")


for port in range(lo, hi + 1):
    try:
        srv = HTTPServer(("", port), H)
        break
    except OSError:
        continue
url = "http://%s:%d" % (socket.getfqdn(), port)
if url_file:
    d = os.path.dirname(url_file)
    tmp = os.path.join(d, ".graphed-secret.tmp")
    with open(tmp, "w") as f:
        f.write(secret_hex)
    os.replace(tmp, os.path.join(d, "graphed-secret"))
    tmp = os.path.join(d, ".driver.url.tmp")
    with open(tmp, "w") as f:
        f.write(url)
    os.replace(tmp, url_file)
print(url, flush=True)
srv.serve_forever()
