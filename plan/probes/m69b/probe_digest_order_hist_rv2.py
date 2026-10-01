"""Hash each pre-m69b frozen dir of the worktree (argv[1]) in three orders: the new key on POSIX, the
new key on PureWindowsPath parts, and the old WindowsPath order (case-folded); plus a one-byte mutation."""
import hashlib, sys
from pathlib import Path, PureWindowsPath
sys.path.insert(0, sys.argv[1] + "/tests/frozen/m69b")
root = Path(sys.argv[1]) / "tests/frozen"
src = (root / "m69b/test_histserv_surface.py").read_text()
want = eval(src[src.index("FROZEN_BEFORE_M69B = {") + len("FROZEN_BEFORE_M69B = "): src.index("}\n", src.index("FROZEN_BEFORE_M69B")) + 1])
def digest(files, mutate=None):
    h = hashlib.sha256()
    for rel in files:
        data = (root / rel).read_bytes()
        if rel == mutate: data += b"x"
        if rel.endswith((".py", ".md")): data = data.replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\0" + data + b"\0")
    return h.hexdigest()[:8]
for name, w in want.items():
    rels = [q.relative_to(root).as_posix() for q in (root / name).rglob("*") if q.is_file() and "__pycache__" not in q.parts]
    posix = sorted(rels, key=lambda r: Path(r).parts)
    win_new = sorted(rels, key=lambda r: PureWindowsPath(r).parts)
    win_old = sorted(rels, key=lambda r: [p.lower() for p in PureWindowsPath(r).parts])
    print(name, "want", w[:8], "posix", digest(posix), "win-new", digest(win_new), "win-old", digest(win_old),
          "mutated", digest(posix, posix[0]), "same-order", posix == win_new)
