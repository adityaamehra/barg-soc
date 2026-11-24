#!/bin/bash
# The whole regression of the FINAL quad-core SoC (every hardware feature on: FP, gshare predictor, L2/L3, posted stores, 32-entry TLBs, WFI halt, L3 write-allocate, PMP,
# GPIO/SPI/I2C, the ten-core GPU cluster), on Verilator only. Run from the repository root:
#   bash demos/quad-soc/tests/regress.sh [scratch dir] [--no-feature ...]      # --no-fp --no-bp --no-hier --no-periph --no-post --no-wfi --no-wa --no-tlb32 --no-pmp --no-gpu (for experiments only)
# Builds the design with demos/quad-soc/tests/mk.sh, then runs: riscv-tests (104 with F and D), four-hart paging, the kernel-pattern tests (demand paging, misaligned accesses, SUM,
# supervisor traps), interrupts (msip ring, PLIC meip, mtip), the GPU kernels on ten cores, four harts on four cores, the memory-system tests, the peripherals.
# The run FAILS (exit 1, "REGRESSION FAILED") on any FAIL line, any TOHOST other than 1, or any "X of Y" with X below Y.
set -e   # a failing step ends the run (FAIL lines are printed first)
S=/tmp/quad5-regress; if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then S=$1; shift; fi
OPTS="$*"
rm -rf "$S"; mkdir -p "$S"
exec > >(tee "$S/all.txt") 2>&1   # every line is also kept, to be checked at the end
V=5
SUITES=rv32ui,rv32um,rv32ua,rv32uc,rv32mi,rv32si; case " $OPTS " in *" --no-fp "*) ;; *) SUITES=$SUITES,rv32uf,rv32ud;; esac
bash demos/quad-soc/tests/mk.sh "$S" $OPTS
N=$S/out; T=demos/quad-soc/tests
R=$(python3 $T/isa_quad.py "$N" --suites $SUITES --jobs 10 | tail -1); echo "$R"; A=${R%% of*}; B=${R#* of }; B=${B%% *}; [ "$A" = "$B" ] || { echo "FAIL: only $R"; exit 1; }
python3 $T/run_paging4.py "$N" | tail -1
for t in demand4 misalign4 sum4 strap4; do echo -n "$t: "; python3 $T/run_c.py "$N" $T/$t.c 3fc100 3fc101 | head -1; done
python3 $T/run_irq4.py "$N"
python3 demos/gpu-cluster/multihart_tests.py "$N" | grep -E "^(PASS|FAIL)"
python3 demos/gpu-cluster/cluster_tests.py "$N" vecadd reduce collatz gemm_i8 gemm_shared conv2d --distinct | grep -E "^(PASS|FAIL)"
if [ "$V" = 5 ]; then   # the memory system: data-cache coherence, capacity pressure, loads while other harts use devices, atomics
  for t in dcache_coh4 amo_mix4 l3_stress4 dc_gpuwr4 post4; do echo -n "$t: "; LIMIT=8000000 python3 $T/run_c.py "$N" $T/$t.c 3fc100 3fc101 --all-harts | head -1; done
  echo -n "dcache_loop: "; python3 $T/run_c.py "$N" $T/dcache_loop.c 3fc100 3fc101 | head -1
fi
echo -n "periph4: "; TB=periph_tb.v LIMIT=2000000 python3 $T/run_c_nogpu.py "$N" $T/periph4.c | head -2
sleep 1
if grep -qE "^FAIL|TOHOST ([02-9]|[0-9]{2,}) |: FAIL|only .* of" "$S/all.txt"; then echo "REGRESSION FAILED (see the FAIL / TOHOST lines above)"; exit 1; fi
echo "REGRESSION PASSED"
