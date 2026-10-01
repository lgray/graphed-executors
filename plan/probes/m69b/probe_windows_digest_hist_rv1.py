"""Frozen m69b `_digest` under POSIX path order vs Windows' case-insensitive Path order (git show of the
frozen tag's files; CI windows legs printed m23 '3b59...b1b33f2', POSIX expects '7cc9...94d08f0')."""
import hashlib, subprocess, sys
repo, tag = sys.argv[1], sys.argv[2]
def files(d):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", tag, f"tests/frozen/{d}"], cwd=repo, capture_output=True, text=True, check=True).stdout.split()
    return [(p[len("tests/frozen/"):], subprocess.run(["git", "show", f"{tag}:{p}"], cwd=repo, capture_output=True, check=True).stdout) for p in out]
for d in ("m23", "m48", "m49"):
    fs = files(d)
    for label, key in (("posix", lambda f: f[0]), ("windows-casefold", lambda f: f[0].lower())):
        h = hashlib.sha256()
        for rel, data in sorted(fs, key=key):
            if rel.endswith((".py", ".md")):
                data = data.replace(b"\r\n", b"\n")
            h.update(rel.encode() + b"\0" + data + b"\0")
        print(d, label, h.hexdigest()[:4] + "..." + h.hexdigest()[-7:])
