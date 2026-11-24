"""Runs the self-checking ELFs of the ACT4 riscv-arch-test framework (make elfs, config barg-quad) on the quad-core SoC's generated Verilog
(Verilator). Hart 0 runs the test (the test's boot code parks harts 1-3); the test ends when tohost is written (1 = pass).

    python3 demos/quad-soc/tests/act4_run.py <assembled netlist dir> [--elfs DIR] [--jobs 8] [--only substr] [--limit CYCLES]
"""
import argparse, concurrent.futures as cf, re, struct, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlsim
import isa_quad as iq

ELFS = Path.home() / "tools/arch-test/act4/work/barg-quad/elfs"


def prep(elf: Path, tmp: Path) -> tuple[Path, int]:
    binf = tmp / (elf.stem + ".bin")
    subprocess.run([iq.OBJCOPY, "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run([iq.NM, str(elf)], capture_output=True, text=True).stdout
    tohost = int(re.search(r"([0-9a-f]+) [A-Za-z] tohost", nm).group(1), 16)
    data = binf.read_bytes()
    data += b"\0" * (-len(data) % 4)
    hexf = tmp / (elf.stem + ".hex")
    hexf.write_text("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", data)))
    return hexf, tohost


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--elfs", default=str(ELFS))
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=2000000)
    ap.add_argument("--traps", action="store_true", help="print the illegal-instruction CSR accesses (mtval of an mcause 2 trap whose word is a CSR instruction), summed over the tests")
    a = ap.parse_args()
    elfs = sorted(p for p in Path(a.elfs).rglob("*.elf") if a.only in p.name)
    exe = iq.compile_quad(Path(a.netlist))
    res = []
    with tempfile.TemporaryDirectory() as t, cf.ThreadPoolExecutor(a.jobs) as ex:
        t = Path(t)
        def one(e):
            try:
                h, th = prep(e, t)
                if a.traps:
                    out = vlsim.run(exe, [f"+HEX={h}", f"+TOHOST={th:x}", f"+LIMIT={a.limit}", "+TRAPLOG"])
                    seen = {int(m.group(2), 16) >> 20 for m in re.finditer(r"TRAP mcause=0*2 mepc=\w+ mtval=(\w+)", out) if False}
                    seen = {int(m.group(1), 16) >> 20 for m in re.finditer(r"TRAP mcause=0*2 mepc=\w+ mtval=(\w+)", out) if int(m.group(1), 16) & 0x7F == 0x73}
                    return e.stem, True, " ".join(f"{c:03x}" for c in sorted(seen))
                return iq.run_one(exe, e.stem, h, th, a.limit)
            except Exception as x:  # noqa: BLE001
                return e.stem, False, f"error: {str(x)[:150]}"
        for name, ok, line in ex.map(one, elfs):
            res.append((name, ok, line))
            if not ok:
                print(f"FAIL {name}: {line}", flush=True)
    if a.traps:
        import collections
        cnt = collections.Counter(c for _, _, l in res for c in l.split())
        print("illegal CSR accesses (address: tests):", dict(sorted(cnt.items())))
        return 0
    npass = sum(1 for r in res if r[1])
    print(f"ACT4: {npass}/{len(res)} passed")
    return 0 if npass == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
