#!/usr/bin/env bash
# Build the UEFI-shell USB stick for the Sultan Qaboos T5820 MMIOH fix.
# Usage:  ./make-usb.sh /dev/sdX      (the whole device, e.g. /dev/sdb — NOT a partition)
#
# What it does:
#   1. Refuses to touch anything that is not a removable USB block device.
#   2. If the stick's first partition is already FAT32/vfat, it is used as-is (no format).
#      Otherwise it prints the single sudo command Malek must run to format it, and exits.
#   3. Mounts it without root (udisksctl), copies:
#         EFI/BOOT/BOOTX64.EFI   <- Shell.efi   (firmware boots this path from removable media)
#         startup.nsh            <- read-only dump script (pass 1)
#      then syncs and unmounts.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEV="${1:-}"
[[ -n "$DEV" && -b "$DEV" ]] || { echo "usage: $0 /dev/sdX  (whole device)"; lsblk -o NAME,SIZE,TRAN,RM,FSTYPE,LABEL,MOUNTPOINT; exit 1; }

NAME="$(basename "$DEV")"
TRAN="$(lsblk -dno TRAN "$DEV" || true)"
RM="$(lsblk -dno RM "$DEV" || true)"
[[ "$TRAN" == "usb" && "$RM" == "1" ]] || { echo "REFUSING: $DEV is not a removable USB device (TRAN=$TRAN RM=$RM)"; exit 2; }

# first partition (sdb1 or nvme-style p1)
PART="$(lsblk -lno NAME "$DEV" | sed -n '2p')"
[[ -n "$PART" ]] || { echo "No partition on $DEV. Format it first:"; echo "  sudo mkfs.vfat -F 32 -n UEFISHELL $DEV   # (or partition it, then format ${DEV}1)"; exit 3; }
PARTDEV="/dev/$PART"
FST="$(lsblk -no FSTYPE "$PARTDEV")"
if [[ "$FST" != "vfat" ]]; then
  echo "Partition $PARTDEV is '$FST', not vfat. Run this once (needs sudo), then re-run me:"
  echo "  sudo mkfs.vfat -F 32 -n UEFISHELL $PARTDEV"
  exit 4
fi

echo "Using $PARTDEV (vfat). Files to be written:"
sha256sum "$HERE/Shell.efi"
MP="$(udisksctl mount -b "$PARTDEV" 2>/dev/null | sed -E 's/.* at (.*)\.?$/\1/' || true)"
[[ -z "$MP" ]] && MP="$(lsblk -no MOUNTPOINT "$PARTDEV")"
[[ -d "$MP" ]] || { echo "Could not mount $PARTDEV"; exit 5; }
echo "Mounted at $MP"

mkdir -p "$MP/EFI/BOOT"
cp "$HERE/Shell.efi"    "$MP/EFI/BOOT/BOOTX64.EFI"
cp "$HERE/startup.nsh"  "$MP/startup.nsh"
sync
echo "--- contents ---"; find "$MP" -maxdepth 3 -type f -exec ls -l {} \;
echo "--- verify copy ---"; sha256sum "$MP/EFI/BOOT/BOOTX64.EFI" "$HERE/Shell.efi"
udisksctl unmount -b "$PARTDEV" >/dev/null && echo "Unmounted. Stick is ready: F12 on the T5820 -> boot the USB (P40 OUT, Secure Boot OFF)."
