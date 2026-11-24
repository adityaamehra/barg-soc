#!/bin/bash
# Installs AMD Vivado into ~/Xilinx from the installer you downloaded into ~/Downloads (the only manual steps are the AMD login and the licence).
#   1. download "AMD Unified Installer for FPGAs & Adaptive SoCs" for Linux (the self-extracting web installer, .bin) into ~/Downloads
#   2. bash demos/fpga/install_vivado.sh auth      extracts the installer and asks for your AMD login (a token is stored in ~/.Xilinx)
#   3. bash demos/fpga/install_vivado.sh config    you pick Vivado, the edition and the devices (tick only what the board needs, it saves tens of GB)
#   4. bash demos/fpga/install_vivado.sh install   batch install into ~/Xilinx (about an hour, no display needed)
#   5. bash demos/fpga/install_vivado.sh finish    system libraries, USB cable drivers (asks for sudo), a settings line for ~/.bashrc, a version check
set -e
X=$HOME/xilinx-installer; D=$HOME/Xilinx; BIN=$(ls -t "$HOME"/Downloads/FPGAs_AdaptiveSoCs_Unified_*_Lin64.bin 2>/dev/null | head -1)
case "$1" in
  auth)    [ -n "$BIN" ] || { echo "put FPGAs_AdaptiveSoCs_Unified_*_Lin64.bin into ~/Downloads first"; exit 1; }
           chmod +x "$BIN"; rm -rf "$X"; script -qec "'$BIN' --keep --noexec --target $X" /dev/null >/dev/null   # the installer wants a terminal; script supplies one
           "$X/xsetup" -b AuthTokenGen ;;
  config)  "$X/xsetup" -b ConfigGen; echo "config written to ~/.Xilinx/install_config.txt"; sed -i "s|^Destination=.*|Destination=$D|" ~/.Xilinx/install_config.txt; grep -E "^(Edition|Destination)" ~/.Xilinx/install_config.txt ;;
  install) "$X/xsetup" --agree XilinxEULA,3rdPartyEULA --batch Install --config ~/.Xilinx/install_config.txt ;;
  finish)  V=$(ls -d "$D"/Vivado/20* | sort | tail -1); echo "Vivado $V"
           sudo bash "$V/scripts/installLibs.sh"
           sudo bash "$D/Vivado/$(basename "$V")/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers" || true
           grep -q "Vivado/.*/settings64.sh" ~/.bashrc || echo "source $V/settings64.sh   # Vivado" >> ~/.bashrc
           bash -c "source $V/settings64.sh && vivado -version | head -2" ;;
  *) sed -n 2,7p "$0" ;;
esac
