"""Runs riscv-tests on the instruction-level model (iss_s.py): the same tests as isa_tile.py runs on the RTL.
    python3 demos/linux-soc/tests/iss_isa.py [--suites rv32uf,rv32ud,...] [--only name,name] [--limit N]"""
import argparse, re, sys, tempfile, importlib.util
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
src = (HERE / "isa_tile.py").read_text().split("def compile_tile")[0]
src = src.replace("rv32imac_zicsr_zifencei", "rv32imafdc_zicsr_zifencei").replace("-mabi=ilp32\"", "-mabi=ilp32d\"")
ns = {"__file__": str(HERE / "isa_tile.py"), "__name__": "isa_tile_lib"}
exec(compile(src, "isa_tile", "exec"), ns)
build, RT, SUITE_DIRS = ns["build"], ns["RT"], ns["SUITE_DIRS"]
spec = importlib.util.spec_from_file_location("iss_s", HERE.parent / "iss_s.py")
iss = importlib.util.module_from_spec(spec)
sys.modules["iss_s"] = iss
spec.loader.exec_module(iss)

ap = argparse.ArgumentParser()
ap.add_argument("--suites", default="rv32uf,rv32ud")
ap.add_argument("--only", default="")
ap.add_argument("--limit", type=int, default=200000)
a = ap.parse_args()
only = set(filter(None, a.only.split(",")))
SUITE_DIRS.update({"rv32uf": "rv32uf", "rv32ud": "rv32ud"})
ok = bad = 0
with tempfile.TemporaryDirectory() as t:
    wd = Path(t)
    for suite in a.suites.split(","):
        for srcf in sorted((RT / "isa" / SUITE_DIRS[suite]).glob("*.S")):
            name = f"{suite}-{srcf.stem}"
            if srcf.stem == "move" or name == "rv32ui-ma_data":     # move is not in upstream rv32ud; ma_data expects misaligned accesses to work (this SoC traps them)
                continue
            if only and name not in only and srcf.stem not in only:
                continue
            try:
                hexf, tohost = build(srcf, wd / name)
            except RuntimeError as e:
                print("FAIL", name, "build:", str(e)[:150]); bad += 1; continue
            words = [int(x, 16) for x in hexf.read_text().split()]
            image = b"".join(w.to_bytes(4, "little") for w in words)
            m = iss.Machine(image)
            off = tohost - iss.RAM_BASE
            n = 0
            while n < a.limit and int.from_bytes(m.ram[off:off + 4], "little") == 0:
                m.step(); n += 1
            v = int.from_bytes(m.ram[off:off + 4], "little")
            if v == 1:
                ok += 1; print("ok  ", name, f"({n} instructions)")
            else:
                bad += 1; print("FAIL", name, "timeout" if v == 0 else f"tohost {v} (check {v >> 1}) at pc {m.pc:x}")
print(f"{ok} of {ok + bad} pass")
sys.exit(1 if bad else 0)
