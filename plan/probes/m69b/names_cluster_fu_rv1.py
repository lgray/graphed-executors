# Frozen m69b row 7's names_cluster, taken verbatim from the frozen file, on the probe's live 5fdb3c0 message.
import re, sys
src = open("tests/frozen/m69b/test_service_order.py").read()
exec(re.search(r"^def names_cluster\(.*?\n(?:    .*\n)+", src, re.M).group(0))
msg = re.search(r"MESSAGE: (.*)", open(sys.argv[1]).read()).group(1)
print("message:", msg)
print("names_cluster(msg, 70):", names_cluster(msg, 70))
print("control names_cluster(msg, 7):", names_cluster(msg, 7), "| control on main's text form:",
      names_cluster("beside the runner's running pilots (cluster 70), which keep", 70))
