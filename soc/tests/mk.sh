#!/bin/bash
# Build, flatten and assemble the FINAL quad-core SoC into <outdir>/out (every hardware feature on).
#   bash demos/quad-soc/tests/mk.sh <outdir> [--no-gpu] [--no-fp] [--no-bp] [--no-hier] [--no-periph] [--no-post] [--no-wfi] [--no-wa] [--no-tlb32] [--no-pmp] [--no-ps2]
# A feature is left out only on request; the names of the intermediate files carry the features that are in (design-quad5-fp-bp-hier-periph-post-wfi-wa-tlb32-pmp.json).
cd "$(dirname "$0")/../../.." || exit 1
S=$1; shift; rm -rf "$S"; mkdir -p "$S"
on() { case " $* " in *" --no-$1 "*) return 1;; esac; return 0; }
FEATS=""; for f in fp bp hier periph post wfi wa tlb32 pmp ps2; do if on $f "$@"; then if [ $f = ps2 ] && ! on periph "$@"; then continue; fi; FEATS="$FEATS-$f"; fi; done
case " $* " in *" --ext-mem "*) FEATS="$FEATS-extmem";; esac
for a in "$@"; do case "$a" in --fpga-caches) FEATS="$FEATS-fc";; --fpga-caches=*) FEATS="$FEATS-fc-$(echo ${a#*=} | tr , - | tr " " "\n" | tr - "\n" | sort | paste -sd-)";; esac; done   # FPGA build: small cache arrays   # FPGA build: the memory model is left out and the AXI4 master is a port
GPUSFX=""; if ! on gpu "$@"; then GPUSFX="-nogpu"; fi
CORE=""; if on fp "$@"; then CORE="$CORE --fp"; fi; if on bp "$@"; then CORE="$CORE --bp"; fi; if on pmp "$@"; then CORE="$CORE --pmp"; fi; if on ps2 "$@" && on periph "$@"; then CORE="$CORE --sext"; fi
python3 demos/linux-soc/build_core.py --mem $CORE > /dev/null
python3 demos/quad-soc/build_quad5.py "$@" | tail -1
n=design-quad5; c=copies5; o=origid5; sfx="$GPUSFX$FEATS"
node packages/backend/dist/cli/ip.js flatten --workspace workspace --design demos/quad-soc/$n$sfx.json --out $S/flat 2>&1 | tail -1
cp demos/quad-soc/$c$sfx.json $S/flat/copies.json; cp demos/quad-soc/$o$sfx.json $S/flat/origid.json
python3 demos/linux-soc/assemble.py $S/flat/design.json $S/out | tail -1
