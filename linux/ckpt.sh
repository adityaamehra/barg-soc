#!/bin/bash
# Keep the simulator's parked checkpoints on disk (they survive a reboot) with CRIU. Needs root for CRIU, so run it with sudo (the password is never stored):
#   sudo bash demos/linux-soc/ckpt.sh save              dump every live checkpoint copy into <checkpoint dir>/criu (the copy keeps running)
#   sudo bash demos/linux-soc/ckpt.sh restore           bring back every checkpoint that has a dump and no live copy (after a reboot), running as your user
# CRIU: ~/tools/criu-4.1/criu (CRIU 4.1 built from source; the packaged 3.16 cannot restore on a 6.x kernel).
set -e
U=${SUDO_USER:-$USER}; H=$(getent passwd "$U" | cut -d: -f6); C=$H/tools/criu-4.1/criu; R=$H/.cache/barg-soc/ckpt
[ -x "$C" ] || { echo "no CRIU at $C"; exit 1; }
for d in "$R"/*/; do
  d=${d%/}
  case "$1" in
    save)
      [ -f "$d/info" ] || continue
      pid=$(cut -d' ' -f1 "$d/info")
      if kill -0 "$pid" 2>/dev/null; then mkdir -p "$d/criu"; "$C" dump -t "$pid" -D "$d/criu" --leave-running --shell-job -o dump.log && chown -R "$U" "$d/criu" && echo "saved $(basename "$d")"; fi ;;
    restore)
      core=$(ls "$d"/criu/core-*.img 2>/dev/null | head -1); [ -n "$core" ] || continue
      pid=$(basename "$core" .img); pid=${pid#core-}
      cyc=$(basename "$d"); cyc=${cyc##*-}
      if ! kill -0 "$pid" 2>/dev/null; then
        mkdir -p "$d"; [ -p "$d/ctl" ] || { rm -f "$d/ctl"; mkfifo "$d/ctl"; chown "$U" "$d/ctl"; }
        "$C" restore -D "$d/criu" -d -o restore.log && echo "$pid $cyc" > "$d/info" && chown "$U" "$d/info" && echo "restored $(basename "$d") as pid $pid"
      fi ;;
    *) echo "usage: sudo bash $0 save|restore"; exit 2 ;;
  esac
done
