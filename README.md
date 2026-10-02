# NVIDIA Tesla P40 in a Dell Precision 5820 Tower: why it won't POST, and the fix (no BIOS flash)

**TL;DR.** A Tesla P40 (or P100, V100, or any card with a large 64-bit BAR) makes a Dell Precision 5820/7820/7920 power-cycle three or four times and halt with no video, even with "Memory Map IO above 4GB" enabled. The firmware ships with its high-MMIO window **zero-sized** (`MmiohBase = 0`, `MmiohSize = 0` in the hidden NVRAM variable `SocketCommonRcConfig`), so the P40's 32 GB BAR1 can never be placed. Setting two 16-bit fields in that variable from a UEFI shell — two bytes changed, nothing flashed — makes the machine POST and boot with the P40 installed. On the 5820 (BIOS 2.41.0) the variable is **115 bytes, not the 114 reported for the 7920/7820**; the fix works the same, but you must dump your own machine's bytes rather than paste someone else's.

> **Who wrote this.** The troubleshooting and this write-up were done by Claude, Anthropic's AI model, working over several sessions with the owner of the machine, who did all the physical work and ran every command. The fix itself was discovered by the people in [xCuri0/ReBarUEFI discussion #331](https://github.com/xCuri0/ReBarUEFI/discussions/331) for a Tesla V100 on a Precision 7920 — this page confirms it for a Tesla P40 on a Precision 5820 and documents the one layout difference.

---

## The machine and the symptom

| | |
|---|---|
| Workstation | Dell Precision 5820 Tower ("T5820"), BIOS **2.41.0**, Xeon W-2123, 32 GB DDR4 RDIMM |
| Display GPU | NVIDIA Quadro K620 in slot 1 |
| Card that would not POST | NVIDIA **Tesla P40** 24 GB (`PCI\VEN_10DE&DEV_1B38`), in slot 2 *or* slot 4 |
| Power to the P40 | Dell PDB's two native 6+2 PCIe leads → one NVIDIA **030-0571-000** "dual 8-pin to 8-pin" adapter → the P40's single CPU/EPS-style 8-pin socket (verified with a multimeter: one row 12.2 V, one row 0 V) |

With the P40 installed and powered: press the power button, fans spin, the machine **powers itself off after 12–14 seconds and restarts, three or four times**, then stops with a **steady white power LED and nothing on the screen** — not even the Dell logo — even with the K620 forced as primary video. Remove the P40 and it boots normally.

Things that were already set or were tried and **did not help**: "Memory Map IO above 4GB" = Enabled (it was already on), Secure Boot off, UEFI-only boot, Primary Video Slot forced to the K620's slot, trying the other x16 slot, re-seating, swapping the power adapter, waiting through many power cycles (a Precision 5820 owner reported that an RTX 3090 Ti needs 5–7 cycles then boots — that's a *consumer* card with a 256 MB BAR; it does not generalise to Tesla cards).

The same failure, unresolved, is on record for a **Tesla P100 in a Precision 5820** ([Dell community](https://www.dell.com/community/en/conversations/precision-fixed-workstations/dell-precision-5820-tower-boot-loop-when-nvidia-tesla-p100-is-installed/651891ac217515760f3983d1)) and for a Tesla P40 in a Precision 7820 ([NVIDIA forum](https://forums.developer.nvidia.com/t/dell-precision-7820-linux-mint-21-3-6-8-kernel-tesla-p40-vs-quadro-p6000/300795), [Win-Raid](https://winraid.level1techs.com/t/dell-precision-t7820-nvidia-tesla-p40-linux-mint/102347), [franfabrizio.dev](https://franfabrizio.dev/posts/troubleshooting-tesla-p40-dell-precision-t7820/)) — where it shows up later, in the OS, as `NVRM: This PCI I/O region assigned to your NVIDIA device is invalid: BAR1 is 0M @ 0x0`.

## Root cause

Datacenter GPUs expose their whole VRAM through a huge 64-bit prefetchable BAR (BAR1): **32 GB on the P40**, 16 GB on the P100. Placing it needs a 64-bit MMIO window above 4 GB ("MMIOH"). On this Dell platform generation the *visible* switch, "Memory Map IO above 4GB", only permits the use of such a window; the window's **base and size** live in Intel RC setup variables that Dell never exposed in Setup, and ship as zero. With a zero-sized window, PCIe resource allocation for the P40 fails during POST, and the 5820's firmware handles that failure by resetting and retrying — hence the power-cycle loop. A consumer card's 256 MB BAR fits below 4 GB, which is why those cards "just need patience" and Tesla cards never work.

## The fix

You change one NVRAM variable from a UEFI shell. **No BIOS flash.** Undo is a CMOS clear.

### What you need
- A FAT32 USB stick with the EDK2 UEFI Shell: download `Shell.efi` (X64) — e.g. tag `edk2-stable201903`: `ShellBinPkg/UefiShell/X64/Shell.efi`, 938,880 bytes, SHA-256 `50437f8f0623a076f350ae937b0054f5912a14bbf9948c9665ca6ae4b0f31e7a` — and save it as `EFI\BOOT\BOOTX64.EFI` on the stick.
- Secure Boot **off** (the shell is unsigned). The P40 **out** of the machine for the shell boot (it can't POST with it in yet).
- The two `startup.nsh` scripts and `make-payload.py` from this repository (optional but recommended — the script gates the write behind a keypress and the Python tool refuses anything it doesn't recognise).

### Step 1 — read your machine's value (read-only)
Boot the stick (F12 → USB). At the shell:
```
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f SocketCommonRcConfig
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f -s fs0:\rc-before.bin SocketCommonRcConfig
```
On this 5820 (BIOS 2.41.0) it printed `DataSize = 0x73` (**115 bytes**) and began:
```
00 00 00 00 00 00 01 02 00 01 00 00 08 06 00 00 ...
^^^^^ MmiohBase=0 ^^^^^ MmiohSize=0
```
For comparison, the working 7920 in #331 reads `00 02 00 00 04 00 03 02 02 01 00 00 06 06 00 00` (114 bytes) and a 7820 `00 02 00 00 04 00 03 02 02 01 00 00 08 04 00 00`. Bytes 6–9 and 12–13 are other platform settings and legitimately differ per model — **never copy another machine's blob**.

### Step 2 — change exactly four bytes, keep every other byte and the length
| Offset | Field | Value | Meaning |
|---|---|---|---|
| 0x00–0x01 | MmiohBase | `00 02` | 0x0200 → window base at 512 GB |
| 0x04–0x05 | MmiohSize | `04 00` | index 4 → 256 GB window (room for two 32 GB BARs) |

`make-payload.py rc-before.bin` does this for you: it parses the `dmpstore -s` file, verifies its CRC32, checks the layout fingerprint (bytes 2–3 = `00 00`, byte 7 = `02`, byte 9 = `01`), refuses lengths other than 114/115, and writes a pass-2 `startup.nsh`.

### Step 3 — write it back and verify
```
setvar SocketCommonRcConfig -guid 4402ca38-808f-4279-bcec-5baf8d59092f -bs -rt -nv =H<your full hex, 230 chars for 115 bytes>
dmpstore -guid 4402ca38-808f-4279-bcec-5baf8d59092f SocketCommonRcConfig
reset
```
The payload this machine used (115 bytes): `000200000400010200010000080600` followed by 200 zeros. The re-dump must start `00 02 00 00 04 00 …`.

### Step 4 — boot straight to the OS, then install the card
Do **not** enter BIOS Setup and save afterwards (see gotchas). Shut down, install the P40, power on.

## Result on this machine
- Before: with the P40 installed, never reached video or the OS; 3–4 power cycles then halt, in either x16 slot.
- After: **5 power cycles** (the NVRAM boot-failure counter had not been cleared), then the Dell logo, then **Windows 11 booted** with the P40 installed. Device Manager: **"NVIDIA Tesla P40 — This device is working properly"**, PCI Slot 4, no Code 12; Windows Update installed driver 26.21.14.4274 (R440/442.74) by itself.
- The Resources tab briefly read *"isn't using any resources because it has a problem"* while the driver install was still pending (*"requires further installation"*); after the restart Windows Update triggered, the card was fully functional:

```
C:\Program Files\NVIDIA Corporation\NVSMI>nvidia-smi.exe -q -d Memory

Driver Version                      : 442.74
CUDA Version                        : 10.2
Attached GPUs                       : 2
GPU 00000000:17:00.0                           <- Tesla P40, slot 4
    FB Memory Usage
        Total                       : 22950 MiB
    BAR1 Memory Usage
        Total                       : 32768 MiB  <- the 32 GB BAR1, placed
GPU 00000000:B3:00.0                           <- Quadro K620, slot 1
    FB Memory Usage
        Total                       : 2048 MiB
    BAR1 Memory Usage
        Total                       : 256 MiB
```

**`BAR1 Total = 32768 MiB` is the line that proves the MMIOH window is doing its job** — it is exactly what the unfixed 7820 reports show as `BAR1 is 0M`.

Repeated with the **second** Tesla P40 in **slot 2** (first card removed): same result — 5 power cycles, Windows up in ~155 s, `nvidia-smi` BAR1 Total 32768 MiB. So the fix is slot-independent on the 5820 (both x16 slots hang off the single CPU), and the 256 GB window leaves room for two 32 GB BARs at once. Note the consistent **5 power cycles on every cold boot with a P40 present** — it does not decay like Dell's boot-failure counter does, so it appears to be fixed firmware behaviour (PCIe retrain/reset) with a large-BAR card installed; budget ~2.5 minutes to the OS.

## Gotchas that will silently undo it
- **BIOS Setup keeps its own copy of this variable and re-zeroes MmiohBase/MmiohSize when you press Save.** Make all other BIOS changes first; write the variable last; afterwards boot straight to the OS. If you ever save in Setup again, redo Step 3.
- **A CMOS/NVRAM clear (the `RTCRST_PSWD` jumper, or pulling the coin cell) wipes it** — that is also your recovery if a mistyped write leaves the machine unable to POST even with the card out.
- Dell's boot-failure recovery cycles the machine three times without video after failed boots. That counter is in NVRAM; it decays with clean boots or is cleared by the CMOS clear above.
- The 5820 **will not power on with the side cover off** (Dell's manual says so — intrusion switch). For bench work with the cover off, hold the switch in or unplug its 3-pin connector and bridge the two black-wire pins.
- The P40's power socket is **CPU/EPS 8-pin pinout**, not PCIe 8-pin, despite the look. Use the 030-0571-000-style adapter and check it with a meter before plugging it into the card.
- The Tesla P40 is passively cooled and needs ducted airflow before any real load.
- In Linux, add `pci=realloc=on` to the kernel command line; do not use `pci=nocrs`. The NVIDIA 580 driver branch is the last to support Pascal.

## Why this is low-risk
It writes **one NVRAM variable** with the shell's `setvar`. It never touches the SPI flash — the thing a BIOS update or a modified-firmware approach (ReBarUEFI's DXE driver) writes to, and the thing that can brick a board. Worst case is a value the firmware rejects, and a CMOS clear returns you to where you started.

## Credits
- [xCuri0/ReBarUEFI discussion #331](https://github.com/xCuri0/ReBarUEFI/discussions/331) — the original discovery (Tesla V100 on a Precision 7920T), the 7820 byte differences, the "Setup flushes it" warning, and a Precision 5820 confirmation with an Intel Arc Pro B70.
- [ReBarUEFI wiki — common issues](https://github.com/xCuri0/ReBarUEFI/wiki/Common-issues-(and-fixes)) for the MMIOH Base/Size background.
- [franfabrizio.dev](https://franfabrizio.dev/posts/troubleshooting-tesla-p40-dell-precision-t7820/) for the most careful public account of the failure on a T7820.

## Files in this repository
- `startup-pass1.nsh` — read-only dump (autoruns from the stick).
- `make-payload.py` — builds the pass-2 script from *your* dump, with the safety gates described above.
- `startup-pass2.nsh.example` — what pass 2 looked like for this machine (your bytes will differ at offsets 6–13).
- `rc-before.bin`, `rc-after.bin` — this 5820's variable before and after (`dmpstore -s` format).
