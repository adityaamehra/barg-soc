"""Run the kernels on the GPU design's own netlist, built from the golden models, and compare with the instruction-level model.

This checks the *design* (design.json: the wiring and what each block is described to do) before any Verilog exists: every
block gets its golden model from golden/ (the storage and counter blocks a generic model of their template), the blocks are
connected through the design's nets, and the result is clocked. A host driver uses the design's host bus exactly as the chip's
host would: it writes the instruction and global memories word by word, writes START_PC and CTRL, waits for done, and reads the
results back. They must equal the instruction-level model's (model/simt.py) and the Python reference's (run_kernel.py).

    python3 demos/simt-gpu/check_pipeline.py              # every kernel
    python3 demos/simt-gpu/check_pipeline.py vecadd -v    # one, with cycle counts
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import run_kernel  # noqa: E402
import simt  # noqa: E402

M = 0xFFFFFFFF
POISON = 0xDEADBEEF


# --------------------------------------------------------------------------- #
# Block models
# --------------------------------------------------------------------------- #

class Comb:
    def __init__(self, fn):
        self.fn = fn
        self.params = list(inspect.signature(fn).parameters)

    def outputs(self, i):
        return self.fn(**{p: i.get(p, 0) for p in self.params})

    def edge(self, i):
        pass


class Storage:
    """The storage template: memory or register file, synchronous or asynchronous read, optional byte enables."""

    def __init__(self, blk):
        s = blk["storage"]
        self.name = blk["name"]
        self.depth, self.sync = s["depth"], s["readStyle"] == "sync"
        names = {p["id"]: p["name"] for p in blk["ports"]}
        self.p = {k: names[v] for k, v in s["ports"].items()}
        width = next(p["width"] for p in blk["ports"] if p["id"] == s["ports"]["rdata"])
        self.mask = (1 << width) - 1
        self.mem = [POISON & self.mask] * self.depth
        self.rreg = {"rdata": POISON & self.mask, "rdata2": POISON & self.mask}

    def outputs(self, i):
        if self.sync:
            return {self.p["rdata"]: self.rreg["rdata"]}
        out = {self.p["rdata"]: self.mem[i.get(self.p["raddr"], 0) % self.depth]}
        if "raddr2" in self.p:
            out[self.p["rdata2"]] = self.mem[i.get(self.p["raddr2"], 0) % self.depth]
        return out

    def edge(self, i):
        if self.sync:
            self.rreg["rdata"] = self.mem[i.get(self.p["raddr"], 0) % self.depth]   # the old contents (sameCycle old)
        if "we" in self.p and i.get(self.p["we"], 0) & 1:
            a = i.get(self.p["waddr"], 0) % self.depth
            data = i.get(self.p["wdata"], 0) & self.mask
            if "be" in self.p:
                be, old = i.get(self.p["be"], 0), self.mem[a]
                for k in range((self.mask.bit_length() + 7) // 8):
                    if be >> k & 1:
                        old = old & ~(0xFF << 8 * k) | data & (0xFF << 8 * k)
                data = old
            self.mem[a] = data


class Counter:
    def __init__(self, blk):
        c = blk["counter"]
        names = {p["id"]: p["name"] for p in blk["ports"]}
        self.count, self.enable = names[c["ports"]["count"]], names[c["ports"]["enable"]]
        width = next(p["width"] for p in blk["ports"] if p["id"] == c["ports"]["count"])
        self.mask, self.value = (1 << width) - 1, 0

    def outputs(self, i):
        return {self.count: self.value}

    def edge(self, i):
        if i.get("rst", 0) & 1:
            self.value = 0
        elif i.get(self.enable, 0) & 1:
            self.value = (self.value + 1) & self.mask


GOLDEN_DIRS = [HERE / "golden"]      # searched in order (the graphics design puts gfx/golden first)


def golden_model(name):
    path = next(d / f"{name}.py" for d in GOLDEN_DIRS if (d / f"{name}.py").exists())
    spec = importlib.util.spec_from_file_location(f"golden_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    classes = [c for c in vars(mod).values() if inspect.isclass(c) and hasattr(c, "outputs") and hasattr(c, "edge")]
    if classes:
        return classes[0]()
    return Comb(getattr(mod, f"golden_{name}"))


# --------------------------------------------------------------------------- #
# The netlist
# --------------------------------------------------------------------------- #

class Netlist:
    def __init__(self, design):
        self.blocks = {b["id"]: b for b in design["blocks"]}
        self.models = {}
        for bid, blk in self.blocks.items():
            if "storage" in blk:
                self.models[bid] = Storage(blk)
            elif "counter" in blk:
                self.models[bid] = Counter(blk)
            else:
                self.models[bid] = golden_model(blk["name"])
        self.port_name = {(bid, p["id"]): p["name"] for bid, blk in self.blocks.items() for p in blk["ports"]}
        self.top_name = {p["id"]: p["name"] for p in design["topLevelPorts"]}
        self.value = {}                      # net id -> value
        self.drives = {}                     # (block id, port name) -> net id, for outputs
        self.inputs_of = {bid: {} for bid in self.blocks}   # block id -> {port name: net id}
        self.top_in, self.top_out = {}, {}
        self.sinks = {}
        for net in design["nets"]:
            nid, d = net["id"], net["driver"]
            self.value[nid] = 0
            if d["blockId"] is None:
                self.top_in[self.top_name[d["portId"]]] = nid
            else:
                self.drives[(d["blockId"], self.port_name[(d["blockId"], d["portId"])])] = nid
            self.sinks[nid] = []
            for s in net["sinks"]:
                if s["blockId"] is None:
                    self.top_out[self.top_name[s["portId"]]] = nid
                else:
                    self.inputs_of[s["blockId"]][self.port_name[(s["blockId"], s["portId"])]] = nid
                    self.sinks[nid].append(s["blockId"])
        self.top = {name: 0 for name in self.top_in}
        self.cycle = 0

    def _inputs(self, bid):
        return {name: self.value[nid] for name, nid in self.inputs_of[bid].items()}

    def settle(self):
        for name, nid in self.top_in.items():
            self.value[nid] = self.top[name]
        dirty = list(self.blocks)
        rounds = 0
        while dirty:
            rounds += 1
            if rounds > 60:
                raise RuntimeError("the netlist does not settle (a combinational loop?)")
            nxt = []
            for bid in dirty:
                out = self.models[bid].outputs(self._inputs(bid))
                for pname, v in out.items():
                    nid = self.drives.get((bid, pname))
                    if nid is None:
                        continue
                    v = 0 if v is None else v
                    if self.value[nid] != v:
                        self.value[nid] = v
                        nxt.extend(self.sinks[nid])
            dirty = list(dict.fromkeys(nxt))

    def clock(self):
        self.settle()
        ins = {bid: self._inputs(bid) for bid in self.blocks}
        for bid, m in self.models.items():
            m.edge(ins[bid])
        self.cycle += 1

    def out(self, name):
        return self.value[self.top_out[name]]


# --------------------------------------------------------------------------- #
# The host
# --------------------------------------------------------------------------- #

class Host:
    def __init__(self, net: Netlist):
        self.n = net

    def idle(self, cycles=1):
        self.n.top.update(host_en=0, host_we=0)
        for _ in range(cycles):
            self.n.clock()

    def write(self, addr, value):
        self.n.top.update(host_en=1, host_we=1, host_addr=addr & M, host_wdata=value & M)
        self.n.clock()
        self.n.top.update(host_en=0, host_we=0)

    def read(self, addr):
        self.n.top.update(host_en=1, host_we=0, host_addr=addr & M)
        self.n.clock()
        self.n.top.update(host_en=0)
        self.n.settle()
        assert self.n.out("host_rvalid") == 1
        return self.n.out("host_rdata")

    def write_bytes(self, addr, data: bytes):
        data = data + bytes(-len(data) % 4)
        for k in range(0, len(data), 4):
            self.write(addr + k, int.from_bytes(data[k:k + 4], "little"))


def run_on_netlist(name: str, seed: int = 1, max_cycles: int = 400_000, verbose: bool = False) -> dict:
    design = json.loads((HERE / "design.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        elf = run_kernel.compile_kernel(name, Path(tmp))
        ref = simt.Gpu(simt.Config())
        syms = run_kernel.load_elf(ref, elf)
        segments = elf_segments(elf)
    inputs, expected = run_kernel.CASES[name](random.Random(seed))

    net = Netlist(design)
    host = Host(net)
    net.top["rst"] = 1
    host.idle(2)
    net.top["rst"] = 0
    for addr, data in segments:
        host.write_bytes(addr, data)
    for sym, raw in inputs.items():
        host.write_bytes(syms[sym][0], raw)
        ref.write(syms[sym][0], raw)
    host.write(0x3000_0004, syms["_start"][0])
    host.write(0x3000_0008, 0)
    start_cycle = net.cycle
    host.write(0x3000_0000, 1)
    diverged = 0
    while True:
        net.settle()
        if net.out("done") or net.out("error"):
            break
        diverged |= net.out("diverged")
        if net.cycle - start_cycle > max_cycles:
            raise AssertionError(f"{name}: no done after {max_cycles} cycles")
        host.idle()
    cycles = net.cycle - start_cycle
    if net.out("error"):
        info = host.read(0x3000_0014)
        raise AssertionError(f"{name}: the core stopped with error cause {info & 15} in warp {info >> 8 & 3} at pc "
                             f"0x{host.read(0x3000_0010):08x}")

    ref.launch(syms["_start"][0])
    ref.run()
    for sym, want in expected.items():
        addr = syms[sym][0]
        got = [host.read(addr + 4 * k) for k in range(len(want))]
        model = ref.read_words(addr, len(want))
        if got != model:
            bad = next(k for k in range(len(want)) if got[k] != model[k])
            raise AssertionError(f"{name}: {sym}[{bad}] netlist 0x{got[bad]:08x}, model 0x{model[bad]:08x}")
        if got != [w & M for w in want]:
            raise AssertionError(f"{name}: {sym} differs from the Python reference")
    if verbose:
        print(f"  {name}: {cycles} cycles on the netlist, {ref.stats.steps} warp instructions in the model, "
              f"IPC {ref.stats.steps / cycles:.2f}; diverged branches seen: {diverged}")
    return {"cycles": cycles, "steps": ref.stats.steps}


def elf_segments(elf: Path) -> list[tuple[int, bytes]]:
    import struct
    raw = elf.read_bytes()
    phoff, = struct.unpack_from("<I", raw, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", raw, 0x2A)
    out = []
    for k in range(phnum):
        p_type, off, _v, paddr, filesz, memsz, _f, _a = struct.unpack_from("<8I", raw, phoff + k * phentsize)
        if p_type == 1 and memsz and paddr < 0x2000_0000:          # instruction and global memory (shared is not loaded)
            out.append((paddr, raw[off: off + filesz] + bytes(memsz - filesz)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kernels", nargs="*", default=list(run_kernel.CASES))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    for name in args.kernels:
        r = run_on_netlist(name, verbose=args.verbose)
        print(f"{name}: OK on the netlist ({r['cycles']} cycles, IPC {r['steps'] / r['cycles']:.2f} warp instructions per cycle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
