# Reintegration checks

1. Assemble the core from BARG's outputs and elaborate it:
   `python3 demos/linux-soc/assemble.py demos/linux-soc/design-core.json /tmp/core_s && cd /tmp/core_s && iverilog -g2012 -o core.vvp top.v blocks.v`
2. Smoke test (the testbench is the instruction memory; the core is alone, with translation off):
   `cp demos/linux-soc/tests/smoke_tb.v /tmp/core_s && cd /tmp/core_s && iverilog -g2012 -o smoke.vvp top.v blocks.v smoke_tb.v && vvp -n smoke.vvp`
   Expected: one store line `addr 00000000 data 0000000c` (addi 5, addi 7, add, sw), no exception.
