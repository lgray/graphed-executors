"""What run_lpc.py's logging (logging.basicConfig(level=INFO), as main() sets it) prints for a service status:
does the line carry the server's submit (started_at) and ready times?"""
import logging

from graphed.services import Launch, ServiceSpec

from graphed_executors.submit import ThreadBackend
from graphed_executors.submit.services import ServiceSet

logging.basicConfig(level=logging.INFO)  # run_lpc.main's call
LISTEN = "import socket, sys, time; s = socket.create_server((sys.argv[1], int(sys.argv[2]))); time.sleep(30)"
spec = ServiceSpec("rv-log", kind="rv", check="tcp", launch=Launch(("{python}", "-c", LISTEN, "{host}", "{port}")))
backend = ThreadBackend(1)
try:
    with ServiceSet([spec], backend) as _:
        pass
finally:
    backend.close()
