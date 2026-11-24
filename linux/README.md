# Linux on the SoC's generated Verilog

**Boot it and use it** (needs the repository as it is on this machine: the netlist is assembled from BARG's accepted blocks, and the firmware image is
`~/linux-work/pico/sbi/platform/generic/firmware/fw_payload.bin`, built by `sw/build.sh`):

```
python3 demos/linux-soc/run_linux.py                                   # a console: type into the shell (Ctrl-A x leaves)
python3 demos/linux-soc/run_linux.py --keys "uname;ls /;free;fork"     # type these for you, each after the prompt, then leave
```

First run builds the netlist and the Verilator simulator (about a minute, cached in `~/.cache/barg-soc`); the shell prompt comes after about two
minutes (about 110 million simulated cycles). It is the quad-core SoC with OpenSBI and Linux 6.6 bringing up four CPUs. Typing is slow because the
UART has a one-byte receive register and Linux polls it.

| File | What |
|---|---|
| `run_linux.py` | the command above |
| `console/host.cpp`, `console/console_tb.v` | the terminal on the UART (DPI-C) |
| `sw/` | device tree, kernel config, init program, build script for the firmware image |
| `iss_s.py` | the Python reference model of the core (golden model); `--trap-trace` lists every trap, to diff against the RTL |
| `tests/` | riscv-tests runner and the boot tools (`boot_quad.py`, `linux_quad_tb.v`) |
| `build_core.py`, `build_tile.py`, `blocks.py`, `golden/`, `rtl/` | the core's design, block specs, hand-written golden models and accepted Verilog |
