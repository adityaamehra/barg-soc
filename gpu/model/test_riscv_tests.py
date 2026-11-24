"""The model's RV32IM against the official riscv-tests (rv32ui and rv32um), with the project's trap-free environment
(scripts/riscv-env, the same one the RISC-V demos use).

Each test runs twice: on one lane, as a CPU; and on all four lanes at once, where every lane must compute the same thing
(the branches stay uniform because every lane has the same data). The test passes when it writes 1 to `tohost`.
Needs riscv64-elf-gcc and a checkout at workspace/riscv-tests (demos/rv32i-pipelined/isa_tests.py makes one); skipped otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import simt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = ROOT / "workspace" / "riscv-tests"
GCC = shutil.which("riscv64-elf-gcc") or shutil.which("riscv64-unknown-elf-gcc")
READY = GCC is not None and (CHECKOUT / "isa" / "rv32ui").is_dir() and (CHECKOUT / "env" / "encoding.h").exists()


def suite_tests(suite: str) -> list[str]:
    if not READY:
        return []
    return sorted(p.stem for p in (CHECKOUT / "isa" / suite).glob("*.S"))


@pytest.fixture(scope="module")
def build(tmp_path_factory) -> Path:
    b = tmp_path_factory.mktemp("rvtests")
    (b / "env" / "p").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "riscv-env" / "p" / "riscv_test.h", b / "env" / "p" / "riscv_test.h")
    shutil.copy(CHECKOUT / "env" / "encoding.h", b / "env" / "encoding.h")
    link = (CHECKOUT / "env" / "p" / "link.ld").read_text()
    (b / "link.ld").write_text(link.replace(". = 0x80000000;", ". = 0x00000000;"))
    return b


def compile_test(b: Path, suite: str, name: str) -> tuple[bytes, int]:
    elf = b / f"{suite}-{name}.elf"
    subprocess.run([GCC, "-march=rv32im_zifencei", "-mabi=ilp32", "-static", "-mcmodel=medany", "-fvisibility=hidden", "-nostdlib",
                    "-nostartfiles", "-I", str(b / "env" / "p"), "-I", str(b / "env"),
                    "-I", str(CHECKOUT / "isa" / "macros" / "scalar"), "-T", str(b / "link.ld"),
                    str(CHECKOUT / "isa" / suite / f"{name}.S"), "-o", str(elf)], check=True, capture_output=True)
    nm = subprocess.run([GCC.replace("gcc", "nm"), str(elf)], check=True, capture_output=True, text=True).stdout
    tohost = next(int(line.split()[0], 16) for line in nm.splitlines() if line.split()[-1] == "tohost")
    binary = elf.with_suffix(".bin")
    subprocess.run([GCC.replace("gcc", "objcopy"), "-O", "binary", str(elf), str(binary)], check=True)
    return binary.read_bytes(), tohost


def run_flat(image: bytes, tohost: int, lanes: int, tmask: int) -> int:
    cfg = simt.Config(lanes=lanes, warps=1, regions=[simt.Region("ram", 0, 0x10000, fetch=True, data=True)])
    gpu = simt.Gpu(cfg)
    gpu.write(0, image)
    result = {}

    def hook(addr, n, value):
        if addr == tohost and value:
            result["v"] = value
    gpu.store_hooks.append(hook)
    gpu.launch(0, tmask=tmask)
    while "v" not in result:
        if gpu.stats.steps > 100_000:
            raise AssertionError("no write to tohost")
        gpu.step()
    return result["v"]


CASES = [("rv32ui", n) for n in suite_tests("rv32ui")] + [("rv32um", n) for n in suite_tests("rv32um")]
# fence_i writes the instruction it then executes: our instruction memory is separate from data memory (the GPU cannot
# do it), but the flat memory of this test can, so it is kept. ma_data needs misaligned accesses, which are errors here.
SKIP = {"ma_data": "misaligned loads and stores are errors in this ISA"}


@pytest.mark.skipif(not READY, reason="needs riscv64-elf-gcc and workspace/riscv-tests")
@pytest.mark.parametrize("suite,name", CASES, ids=[f"{s}-{n}" for s, n in CASES])
def test_riscv_test(build, suite, name):
    if name in SKIP:
        pytest.skip(SKIP[name])
    image, tohost = compile_test(build, suite, name)
    one = run_flat(image, tohost, lanes=1, tmask=1)
    assert one == 1, f"FAIL, test case {one >> 1}"
    four = run_flat(image, tohost, lanes=4, tmask=0xF)
    assert four == 1, f"FAIL on 4 lanes, test case {four >> 1}"
