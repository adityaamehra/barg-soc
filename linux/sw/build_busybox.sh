#!/bin/bash
# A BusyBox shell for the BARG SoC: BusyBox 1.36.1 (static, musl, rv32) as the initramfs, with the same OpenSBI + Linux build as build.sh.
#   bash demos/linux-soc/sw/build_busybox.sh <work dir as for build.sh>
# Output: <work>/pico-bb/sbi/platform/generic/firmware/fw_payload.bin (run it with: run_linux.py --image <that file>).
# Downloads busybox-1.36.1.tar.bz2 once (checked against the SHA-256 in Buildroot's package/busybox/busybox.hash) and applies Buildroot's patches.
set -euo pipefail
W=$(realpath "$1"); SW=$(dirname "$(realpath "$0")"); BB=$W/busybox-bb
export PATH=$W/riscv32-ilp32d--musl--stable-2024.05-1/bin:$W/kenv/bin:$PATH
X=riscv32-buildroot-linux-musl-
mkdir -p "$BB/dl"
TB=$BB/dl/busybox-1.36.1.tar.bz2
[ -f "$TB" ] || curl -fL --retry 3 -o "$TB" https://www.busybox.net/downloads/busybox-1.36.1.tar.bz2
WANT=$(awk '$1=="sha256" && $3 ~ /busybox-1.36.1/ {print $2}' "$W/buildroot-2024.02.9/package/busybox/busybox.hash")
echo "$WANT  $TB" | sha256sum -c -
if [ ! -x "$BB/src/busybox" ]; then
  rm -rf "$BB/src"; mkdir -p "$BB/src"; tar -xjf "$TB" -C "$BB/src" --strip-components=1
  for p in "$W"/buildroot-2024.02.9/package/busybox/*.patch; do patch -d "$BB/src" -p1 -s < "$p"; done
  make -C "$BB/src" defconfig >/dev/null
  sed -i -e 's/^# CONFIG_STATIC is not set/CONFIG_STATIC=y/' -e 's/^CONFIG_TC=y/# CONFIG_TC is not set/' \
         -e "s#^CONFIG_CROSS_COMPILER_PREFIX=.*#CONFIG_CROSS_COMPILER_PREFIX=\"$X\"#" -e 's/^CONFIG_FEATURE_HAVE_RPC=y/# CONFIG_FEATURE_HAVE_RPC is not set/' \
         -e 's/^CONFIG_HWCLOCK=y/# CONFIG_HWCLOCK is not set/'   # hwclock needs settimeofday, which 32-bit RISC-V does not have (and there is no RTC) "$BB/src/.config"
  grep -q '^CONFIG_STATIC=y' "$BB/src/.config" || echo 'CONFIG_STATIC=y' >> "$BB/src/.config"
  (yes "" || true) | make -C "$BB/src" oldconfig >/dev/null
  make -C "$BB/src" -j"$(nproc)" >"$BB/build.log" 2>&1 || { tail -30 "$BB/build.log"; exit 1; }
fi
rm -rf "$BB/rootfs"; mkdir -p "$BB/rootfs"
make -C "$BB/src" CONFIG_PREFIX="$BB/rootfs" install >/dev/null
mkdir -p "$BB/rootfs"/{proc,sys,tmp,root,mnt,etc,usr/bin,usr/sbin}
for c in "$SW"/prog/*.c; do "${X}gcc" -Os -static -Wall -o "$BB/rootfs/bin/$(basename "$c" .c)" "$c"; done   # small demo programs (the mouse cursor)
install -m 0755 "$SW/busybox/init" "$BB/rootfs/init"
install -m 0644 "$SW/busybox/motd" "$BB/rootfs/etc/motd"
printf 'root:x:0:0:root:/root:/bin/sh\n' > "$BB/rootfs/etc/passwd"; printf 'root:x:0:\n' > "$BB/rootfs/etc/group"
cp "$SW/busybox/nodes.list" "$BB/nodes.list"
file "$BB/rootfs/bin/busybox" | cut -c1-120; ls "$BB/rootfs/bin" | wc -l
P_DIR=${P_DIR:-$W/pico-bb} ROOTFS_SOURCE="$BB/rootfs $BB/nodes.list" bash "$SW/build.sh" "$W"
