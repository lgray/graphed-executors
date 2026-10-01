"""Run design.rst "Filling on histserv servers" code blocks verbatim in sequence (cwd = a temp dir) and
compare each block's stdout with the "Printed output::" block after it."""
import contextlib, io, os, re, sys, tempfile
text = open(sys.argv[1]).read()
sec = text[text.index(".. _histserv:"):text.index("Not supported yet")]
parts = re.split(r"\n(\.\. code-block:: python|Printed output::)\n", sec)
blocks, i = [], 1
while i < len(parts):
    body = parts[i + 1]
    lines = body.split("\n"); out = []
    for line in lines[1:]:
        if line.strip() and not line.startswith("    "):
            break
        out.append(line[4:])
    blocks.append((parts[i], "\n".join(out).strip("\n") + "\n")); i += 2
os.chdir(tempfile.mkdtemp()); g = {}
pending = None
for kind, body in blocks:
    if kind.startswith(".. code-block"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(body, "<docs>", "exec"), g)
        pending = buf.getvalue()
    else:
        print("MATCH" if pending.strip() == body.strip() else f"DIFF\n got: {pending!r}\n doc: {body!r}")
