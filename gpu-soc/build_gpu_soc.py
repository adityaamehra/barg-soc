"""Stage G3: the NuttX SoC (stage 4, 16 MB, `nuttx-soc-imac-16mb`) with the SIMT GPU with graphics (`simt-gpu-gfx`) as a device.

    python3 demos/gpu-soc/build_gpu_soc.py        # writes demos/gpu-soc/design.json (id `gpu-soc`)

BARG has no hierarchy, so the design is a flat merge:
  * every SoC block as it is, except region_decode, bus_ctl and io_mux, which gain the GPU region (regenerated);
  * every GPU block renamed: block id b_<x> -> b_g_<x>, name and module <x> -> g_<x> (its RTL is carried over with only the module
    line renamed), its nets prefixed g_; the GPU's clock and reset are the SoC's;
  * a new block, gpu_bridge, between the memory stage and the GPU's host bus (a store is one host write; a load returns the result
    of the previous GPU read and starts its own);
  * new top-level outputs: the GPU's status (gpu_running, gpu_done, gpu_error) and its display (gpu_hsync, gpu_vsync, gpu_de,
    gpu_rgb).
The GPU's window is 16 MB at 0x3000_0000 (bits 31:24 = 0x30); the offsets are in gpu_bridge's description.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).parent
DEMOS = HERE.parent
SOC = DEMOS / "nuttx-soc" / "design-a-16mb.json"
GPU = DEMOS / "simt-gpu" / "gfx" / "design.json"
W = 32


def port(pid, name, direction, width, role):
    return {"id": pid, "name": name, "direction": direction, "width": width, "role": role}


def i(name, width, role="data"):
    return port(f"p_{name}", name, "in", width, role)


def o(name, width, role="data"):
    return port(f"p_{name}", name, "out", width, role)


def block(bid, name, description, ports, reset="none", latency=0):
    return {"id": bid, "name": name, "tier": "T1", "moduleName": name, "description": " ".join(description.split()),
            "ports": ports, "clockDomain": "main", "resetStyle": reset, "latencyCycles": latency, "verified": False}


REGION_DECODE = block("b_region_decode", "region_decode", """
    Combinational address decoder for the data side, in the memory stage. addr is the 32-bit address of an access. There are five
    regions that do not overlap, and every other address belongs to none. The RAM is the 16 MB from 80000000 to 80FFFFFF
    hexadecimal: bits 31:24 of addr are 10000000. The CLINT is the 64 KB from 02000000 to 0200FFFF: bits 31:16 of addr are
    0000001000000000. The PLIC is the 64 MB from 0C000000 to 0FFFFFFF: bits 31:26 of addr are 000011. The UART is the 4 KB from
    10000000 to 10000FFF: bits 31:12 of addr are 00010000000000000000. The GPU is the 16 MB from 30000000 to 30FFFFFF: bits 31:24
    of addr are 00110000. For instance the first 4 KB of the RAM are the addresses whose bits 31:12 of addr are
    10000000000000000000, and the first 4 KB of the GPU those whose bits 31:12 of addr are 00110000000000000000. sel_ram,
    sel_clint, sel_plic, sel_uart and sel_gpu are 1 for the region addr is in and 0 otherwise; is_io is 1 when addr is in the
    CLINT, PLIC, UART or GPU region. No clock, no reset, no state.
""", [i("addr", W, "addr"), o("sel_ram", 1, "control"), o("sel_clint", 1, "control"), o("sel_plic", 1, "control"),
      o("sel_uart", 1, "control"), o("sel_gpu", 1, "control"), o("is_io", 1, "control")])

BUS_CTL = block("b_bus_ctl", "bus_ctl", """
    Combinational. The write and read strobes of the data-side regions, in the memory stage. sel_ram, sel_clint, sel_plic, sel_uart
    and sel_gpu say which region the access is in (at most one is 1). memwrite is 1 for a store that is really going to happen (it
    has already been cancelled for an exception or a trap). ram_we, clint_we, plic_we, uart_we and gpu_we are memwrite and the
    matching select: 1 when memwrite is 1 and that select is 1, 0 otherwise. memsrc is the write-back source of the instruction in
    the memory stage: a load is memsrc 01 (FROM_MEMORY). valid is 1 when the instruction in the memory stage is a real one, xcpt is
    1 when it has raised an exception and kill is 1 when an older instruction is trapping in write-back this cycle. A device read
    happens, and so can have a side effect, only when memsrc is 01, valid is 1, xcpt is 0 and kill is 0: plic_re, uart_re and
    gpu_re are 1 when that holds and sel_plic, sel_uart or sel_gpu respectively is 1, and 0 otherwise. No clock, no reset, no
    state.
""", [i("memwrite", 1, "control"), i("memsrc", 2, "control"), i("valid", 1, "control"), i("xcpt", 1, "control"),
      i("kill", 1, "control"), i("sel_ram", 1, "control"), i("sel_clint", 1, "control"), i("sel_plic", 1, "control"),
      i("sel_uart", 1, "control"), i("sel_gpu", 1, "control"), o("ram_we", 1, "control"), o("clint_we", 1, "control"),
      o("plic_we", 1, "control"), o("uart_we", 1, "control"), o("gpu_we", 1, "control"), o("plic_re", 1, "control"),
      o("uart_re", 1, "control"), o("gpu_re", 1, "control")])

IO_MUX = block("b_io_mux", "io_mux", """
    Combinational. y is clint_rdata when sel_clint is 1, plic_rdata when sel_plic is 1, uart_rdata when sel_uart is 1, gpu_rdata when
    sel_gpu is 1, and 0 when none of the four is 1. At most one select is 1 at a time. No clock, no reset, no state.
""", [i("clint_rdata", W), i("plic_rdata", W), i("uart_rdata", W), i("gpu_rdata", W), i("sel_clint", 1, "control"),
      i("sel_plic", 1, "control"), i("sel_uart", 1, "control"), i("sel_gpu", 1, "control"), o("y", W)])

GPU_BRIDGE = block("b_gpu_bridge", "gpu_bridge", """
    Bridge from the SoC's memory stage to the GPU's host bus. Inputs: gpu_we (a store to the GPU window that is really happening),
    gpu_re (a load from it that is really happening), addr (32 bits, the access address), wdata (32, the store data), memtype (3,
    the access type: 2 is a word; 6 and 7 are reserved codes that act as a word; every other code is narrower or no access),
    host_rdata (32) and host_rvalid from the host bus. Outputs: host_en, host_we, host_addr (32), host_wdata (32) to the host bus,
    and rdata (32), what a load from the window returns.
    Translation, with off = addr bits 23:0: off from 000000 to 00FFFF hexadecimal is mapped to host address 30000000 | off bits
    15:0 (control registers); 010000 to 0107FF to off bits 10:0, zero-extended (instruction memory); 020000 to 021FFF to 10000000 |
    off bits 12:0 (global memory); 030000 to 030FFF to 20000000 | off bits 11:0 (shared memory); 100000 to 1257FF to 40000000 |
    off bits 17:0 (video memory); 140000 to 1657FF to 40040000 | off bits 17:0 (depth memory); 180000 to 1807FF to 50000000 | off
    bits 10:0 (texture). Every other off is unmapped. host_addr is the mapped host address, 0 when unmapped.
    Outputs, at once: word = (memtype is 2, 6 or 7); host_we = mapped & gpu_we & word; host_en = host_we | (mapped & gpu_re);
    host_wdata = wdata; rdata = host_rdata when host_rvalid is 1, otherwise the register rdata_r. So a narrower store, or any
    access to an unmapped offset, is dropped.
    One register, rdata_r (32 bits): on each rising edge it becomes 0 when rst is 1, else takes host_rdata when host_rvalid is 1,
    else keeps its value. The host bus answers a read one cycle after the request (host_rvalid = 1 then), so a load returns the
    result of the previous GPU read and starts its own: a driver reads a GPU address twice and keeps the second value, and two
    loads in consecutive cycles work because the second sees host_rdata directly.
""", [port("p_clk", "clk", "in", 1, "clock"), port("p_rst", "rst", "in", 1, "reset"), i("gpu_we", 1, "control"),
      i("gpu_re", 1, "control"), i("addr", W, "addr"), i("wdata", W), i("memtype", 3, "control"), i("host_rdata", W),
      i("host_rvalid", 1, "valid"), o("host_en", 1, "valid"), o("host_we", 1, "control"), o("host_addr", W, "addr"),
      o("host_wdata", W), o("rdata", W)], reset="sync", latency=1)

STATUS_OUT = [("running", "gpu_running", 1), ("done", "gpu_done", 1), ("error", "gpu_error", 1), ("diverged", "gpu_diverged", 1),
              ("hsync", "gpu_hsync", 1), ("vsync", "gpu_vsync", 1), ("de", "gpu_de", 1), ("rgb", "gpu_rgb", 16)]


def g_name(n: str) -> str:
    return f"g_{n}"


def g_id(b: str | None) -> str | None:
    return None if b is None else "b_g_" + b[2:]


def design() -> dict:
    soc, gpu = json.loads(SOC.read_text()), json.loads(GPU.read_text())
    new = {"region_decode": REGION_DECODE, "bus_ctl": BUS_CTL, "io_mux": IO_MUX}
    blocks = [new.get(b["name"], b) for b in soc["blocks"]] + [GPU_BRIDGE]
    for b in gpu["blocks"]:
        b = copy.deepcopy(b)
        b["id"], b["name"], b["moduleName"] = g_id(b["id"]), g_name(b["name"]), g_name(b["moduleName"])
        b["verified"] = False
        blocks.append(b)
    nets = copy.deepcopy(soc["nets"])
    by_name = {n["name"]: n for n in nets}
    soc_top = {p["id"]: p for p in soc["topLevelPorts"]}
    gpu_top = {p["id"]: p for p in gpu["topLevelPorts"]}
    top = list(soc["topLevelPorts"])

    def sink(bid, pid):
        return {"blockId": bid, "portId": pid}

    def add_sinks(name, *s):
        by_name[name]["sinks"].extend(sink(b, p) for b, p in s)

    def new_net(name, width, driver, sinks):
        n = {"id": f"n_{len(nets) + 1:03d}", "name": name, "width": width, "driver": driver, "sinks": list(sinks),
             "kind": "bus" if width > 1 else "wire", "pipelineStage": 0}
        nets.append(n)
        by_name[name] = n
        return n

    # the SoC side of the GPU: the memory stage to the bridge, the bridge to io_mux
    add_sinks("mem_alu_y", ("b_gpu_bridge", "p_addr"))
    add_sinks("mem_store_data", ("b_gpu_bridge", "p_wdata"))
    add_sinks("mem_memtype", ("b_gpu_bridge", "p_memtype"))
    clock = next(n for n in nets if n["driver"] == {"blockId": None, "portId": "t_clk"})
    reset = next(n for n in nets if n["driver"] == {"blockId": None, "portId": "t_rst"})
    clock["sinks"].append(sink("b_gpu_bridge", "p_clk"))
    reset["sinks"].append(sink("b_gpu_bridge", "p_rst"))
    new_net("sel_gpu", 1, sink("b_region_decode", "p_sel_gpu"), [sink("b_bus_ctl", "p_sel_gpu"), sink("b_io_mux", "p_sel_gpu")])
    new_net("gpu_we", 1, sink("b_bus_ctl", "p_gpu_we"), [sink("b_gpu_bridge", "p_gpu_we")])
    new_net("gpu_re", 1, sink("b_bus_ctl", "p_gpu_re"), [sink("b_gpu_bridge", "p_gpu_re")])
    new_net("gpu_rdata", W, sink("b_gpu_bridge", "p_rdata"), [sink("b_io_mux", "p_gpu_rdata")])

    # the GPU's nets, renamed; its top-level ports become the SoC's clock and reset, the bridge, or new top-level outputs
    host_in = {"t_host_en": "p_host_en", "t_host_we": "p_host_we", "t_host_addr": "p_host_addr", "t_host_wdata": "p_host_wdata"}
    host_out = {"t_host_rdata": "p_host_rdata", "t_host_rvalid": "p_host_rvalid"}
    status = {f"t_{a}": (f"t_{b}", b, w) for a, b, w in STATUS_OUT}
    for n in gpu["nets"]:
        drv = n["driver"]
        sinks = [s for s in n["sinks"] if s["blockId"] is not None]
        sinks = [sink(g_id(s["blockId"]), s["portId"]) for s in sinks]
        tops = [s["portId"] for s in n["sinks"] if s["blockId"] is None]
        if drv["blockId"] is None and drv["portId"] in ("t_clk", "t_rst"):
            (clock if drv["portId"] == "t_clk" else reset)["sinks"].extend(sinks)
            continue
        driver = sink("b_gpu_bridge", host_in[drv["portId"]]) if drv["blockId"] is None else sink(g_id(drv["blockId"]), drv["portId"])
        for t in tops:
            if t in host_out:
                sinks.append(sink("b_gpu_bridge", host_out[t]))
            else:
                tid, name, width = status[t]
                top.append({"blockId": None, **port(tid, name, "out", width, "control" if width == 1 else "data")})
                sinks.append({"blockId": None, "portId": tid})
        new_net(g_name(n["name"]), n["width"], driver, sinks)
    for p in soc_top.values():
        assert p["id"] not in gpu_top or p["id"] in ("t_clk", "t_rst"), p
    d = {k: v for k, v in soc.items() if k not in ("blocks", "nets", "topLevelPorts")}
    d.update({"id": "gpu-soc", "name": "NuttX SoC (RV32IMAC, 16 MB) with the SIMT GPU with graphics as a device at 0x3000_0000",
              "createdAt": "2026-11-20T00:00:00.000Z", "blocks": blocks, "nets": nets, "topLevelPorts": top})
    return d


def check(d: dict) -> None:
    """Every input port of every block has exactly one driving net; every net's ends exist."""
    ports = {(b["id"], p["id"]): p for b in d["blocks"] for p in b["ports"]}
    tops = {p["id"]: p for p in d["topLevelPorts"]}
    driven = {}
    for n in d["nets"]:
        dr = n["driver"]
        assert (dr["blockId"] is None and dr["portId"] in tops) or (dr["blockId"], dr["portId"]) in ports, (n["name"], dr)
        for s in n["sinks"]:
            assert (s["blockId"] is None and s["portId"] in tops) or (s["blockId"], s["portId"]) in ports, (n["name"], s)
            if s["blockId"] is not None:
                assert (s["blockId"], s["portId"]) not in driven, ("driven twice", s, n["name"], driven.get((s["blockId"], s["portId"])))
                driven[(s["blockId"], s["portId"])] = n["name"]
    missing = [k for k, p in ports.items() if p["direction"] == "in" and k not in driven]
    assert not missing, f"undriven inputs: {missing[:10]}"
    assert len({b["id"] for b in d["blocks"]}) == len(d["blocks"]) and len({b["moduleName"] for b in d["blocks"]}) == len(d["blocks"])


def main() -> None:
    d = design()
    check(d)
    out = HERE / "design.json"
    out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: {len(d['blocks'])} blocks, {len(d['nets'])} nets, {len(d['topLevelPorts'])} top-level ports")


if __name__ == "__main__":
    main()
