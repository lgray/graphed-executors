"""MEMORYSTATUSEX as physical_memory_mb declares it: field offsets and size vs the Win32 layout (two DWORDs,
then seven DWORDLONGs: 8..56, size 64). Run on any OS; the declaration is built from the source text."""
import ast, ctypes, sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
cls = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef) and n.name == "_MemoryStatusEx")
ns: dict = {"ctypes": ctypes}
exec(compile(ast.Module(body=[cls], type_ignores=[]), "decl", "exec"), ns)
S = ns["_MemoryStatusEx"]
want = {"dwLength": 0, "dwMemoryLoad": 4, "ullTotalPhys": 8, "ullAvailPhys": 16, "ullTotalPageFile": 24,
        "ullAvailPageFile": 32, "ullTotalVirtual": 40, "ullAvailVirtual": 48, "ullAvailExtendedVirtual": 56}
got = {name: getattr(S, name).offset for name, _ in S._fields_}
print("sizeof", ctypes.sizeof(S), "(want 64); offsets match Win32:", got == want, got if got != want else "")
