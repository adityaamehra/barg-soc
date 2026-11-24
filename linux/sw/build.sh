#!/bin/bash
# Pico Linux for the BARG SoC: OpenSBI 1.5.1 + Linux 6.6.63 (tinyconfig + barg.config: RV32, Sv32, 8250 polled, initramfs) + init.c.
# The SoC has F and D now: CONFIG_FPU=y and the device tree says rv32imafdc (FPU=n DTS=sw/barg-nofp.dts SBI_ISA=rv32imac_zicsr_zifencei builds for the integer-only core).
#   bash demos/linux-soc/sw/build.sh <work dir with linux-6.6.63/, opensbi-1.5.1/, the Bootlin riscv32 musl toolchain, kenv/ (flex, bison)>
# Output: <work>/pico/sbi/platform/generic/firmware/fw_payload.bin, a flat image for 0x8000_0000 (kernel at +4 MB, DTB built in).
set -euo pipefail
W=$(realpath "$1"); SW=$(dirname "$(realpath "$0")"); P=${P_DIR:-$W/pico}; mkdir -p "$P"   # P_DIR: another output directory (build_busybox.sh uses pico-bb)
export PATH=$W/riscv32-ilp32d--musl--stable-2024.05-1/bin:$W/kenv/bin:$PATH
X=riscv32-buildroot-linux-musl-
if [ -n "${ROOTFS_SOURCE:-}" ]; then
  INITRAMFS_SRC="$ROOTFS_SOURCE"      # a space-separated list of directories and cpio list files (see the kernel's gen_initramfs.sh)
else
  "${X}gcc" -march=rv32imac_zicsr -mabi=ilp32 -Os -ffreestanding -fno-builtin -nostdlib -static -Wl,--gc-sections -o "$P/init" "$SW/init.c" -lgcc 2>/dev/null \
    || riscv-none-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -Os -ffreestanding -fno-builtin -nostdlib -static -Wl,--gc-sections -o "$P/init" "$SW/init.c" -lgcc
  cp "$SW/motd" "$P/motd"; sed "s#@SW@#$P#g" "$SW/initramfs.list" > "$P/initramfs.list"
  INITRAMFS_SRC="$P/initramfs.list"
fi
sed "s#^CONFIG_INITRAMFS_SOURCE=.*#CONFIG_INITRAMFS_SOURCE=\"$INITRAMFS_SRC\"#" "$SW/barg.config" > "$P/barg.config"
sed -i "s/^CONFIG_FPU=.*/CONFIG_FPU=${FPU:-y}/" "$P/barg.config"   # FPU=n for the integer-only core
K=$P/kbuild; M="make -C $W/linux-6.6.63 ARCH=riscv CROSS_COMPILE=$X O=$K"
# the framebuffer driver of the GPU's video memory (sw/linux/barg_fb.c) goes into the kernel tree
cp "$SW/linux/barg_fb.c" "$W/linux-6.6.63/drivers/video/fbdev/barg_fb.c"
grep -q FB_BARG "$W/linux-6.6.63/drivers/video/fbdev/Kconfig" || sed -i '/^config FB_SIMPLE$/i config FB_BARG\n\ttristate "BARG SoC GPU framebuffer"\n\tdepends on FB \&\& OF\n\tselect FB_SYS_FILLRECT\n\tselect FB_SYS_COPYAREA\n\tselect FB_SYS_IMAGEBLIT\n\tselect FB_SYS_FOPS\n\tselect FB_DEFERRED_IO\n\thelp\n\t  320x240 RGB565 framebuffer in the video memory of the BARG SoC GPU (word stores through a deferred copy).\n' "$W/linux-6.6.63/drivers/video/fbdev/Kconfig"
grep -q barg_fb "$W/linux-6.6.63/drivers/video/fbdev/Makefile" || echo 'obj-$(CONFIG_FB_BARG) += barg_fb.o' >> "$W/linux-6.6.63/drivers/video/fbdev/Makefile"
$M tinyconfig >/dev/null
"$W/linux-6.6.63/scripts/kconfig/merge_config.sh" -m -O "$K" "$K/.config" "$P/barg.config" >/dev/null
$M olddefconfig >/dev/null
$M -j"$(nproc)" Image >/dev/null
"$K/scripts/dtc/dtc" -I dts -O dtb -o "$P/barg.dtb" "${DTS:-$SW/barg.dts}"
make -C "$W/opensbi-1.5.1" O="$P/sbi" PLATFORM=generic CROSS_COMPILE=$X PLATFORM_RISCV_XLEN=32 PLATFORM_RISCV_ISA=${SBI_ISA:-rv32imafdc_zicsr_zifencei} \
  PLATFORM_RISCV_ABI=ilp32 FW_PAYLOAD_PATH="$K/arch/riscv/boot/Image" FW_FDT_PATH="$P/barg.dtb" -j"$(nproc)" >/dev/null
ls -la "$P/sbi/platform/generic/firmware/fw_payload.bin"
