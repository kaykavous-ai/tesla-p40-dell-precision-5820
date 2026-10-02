#!/usr/bin/env python3
"""
Build the pass-2 `setvar` payload for SocketCommonRcConfig from THIS machine's dump.

Accepts, in order of preference:
  * rc-before.bin as written by `dmpstore -s`  (structured: name, GUID, attributes, data, CRC32)
  * raw data bytes (file whose length is the data size)
  * the hex text shown on screen by `dmpstore` (offsets / *ascii* gutters tolerated), or "-" for stdin

Changes ONLY bytes 0-1 (MmiohBase -> 0x0200 = 512 GB) and 4-5 (MmiohSize -> index 0x0004 = 256 GB).
Every other byte is preserved verbatim, at the dumped length.

Safety gates (any failure -> no output file):
  * GUID in the save file must be 4402ca38-808f-4279-bcec-5baf8d59092f, attributes 0x07
  * CRC32 in the save file must verify (proves the parse is right)
  * data length must be 114 (7920/7820 layout) or 115 (5820 BIOS 2.41.0 layout)
  * layout fingerprint: bytes 2-3 == 00 00, byte 7 == 0x02, byte 9 == 0x01  (true on every known dump)
  * bytes 0-1 and 4-5 must currently be zero (we only ever turn the window ON from OFF)
"""
import re, struct, sys, zlib, pathlib

GUID_STR = "4402ca38-808f-4279-bcec-5baf8d59092f"
GUID_BYTES = struct.pack("<IHH", 0x4402ca38, 0x808f, 0x4279) + bytes.fromhex("bcec5baf8d59092f")
NAME = "SocketCommonRcConfig"
OK_LENS = (114, 115)

def parse_dmpstore_save(blob: bytes):
    """Return (data, attrs) if blob is a dmpstore -s record for our variable, else None."""
    if len(blob) < 8:
        return None
    name_size, data_size = struct.unpack_from("<II", blob, 0)
    if name_size != (len(NAME) + 1) * 2:
        return None
    off = 8
    name = blob[off:off + name_size].decode("utf-16-le").rstrip("\x00"); off += name_size
    guid = blob[off:off + 16]; off += 16
    attrs = struct.unpack_from("<I", blob, off)[0]; off += 4
    data = blob[off:off + data_size]; off += data_size
    crc_stored = struct.unpack_from("<I", blob, off)[0]; off += 4
    if name != NAME:
        sys.exit(f"REFUSING: save file is for variable '{name}', not {NAME}")
    if guid != GUID_BYTES:
        sys.exit(f"REFUSING: GUID in save file is {guid.hex()}, not {GUID_STR}")
    if attrs != 0x07:
        sys.exit(f"REFUSING: attributes are 0x{attrs:02x}, expected 0x07 (NV|BS|RT)")
    if len(data) != data_size or off != len(blob):
        sys.exit("REFUSING: save file is truncated or has trailing bytes")
    # CRC32 covers the record up to (not including) the CRC itself.
    crc_calc = zlib.crc32(blob[: off - 4]) & 0xFFFFFFFF
    if crc_calc != crc_stored:
        sys.exit(f"REFUSING: CRC32 mismatch (stored {crc_stored:08x}, computed {crc_calc:08x}) -- file damaged?")
    print(f"save-file check    : name OK, GUID OK, attrs 0x07 OK, CRC32 {crc_stored:08x} OK, DataSize 0x{data_size:x} ({data_size})")
    return data

def parse_hex_text(text: str) -> bytes:
    pairs = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[0-9A-Fa-f]{8}:\s*", "", line)
        line = re.sub(r"\*.*?\*\s*$", "", line)
        pairs += re.findall(r"\b[0-9A-Fa-f]{2}\b", line)
    if not pairs:
        sys.exit("no hex pairs found in input")
    return bytes(int(h, 16) for h in pairs)

def read_input(src: str) -> bytes:
    blob = sys.stdin.buffer.read() if src == "-" else pathlib.Path(src).read_bytes()
    data = parse_dmpstore_save(blob)
    if data is not None:
        return data
    if len(blob) in OK_LENS:
        print("input treated as raw data bytes")
        return blob
    try:
        return parse_hex_text(blob.decode("utf-8"))
    except UnicodeDecodeError:
        sys.exit(f"{src}: not a dmpstore save, not raw data, not text")

def row(b): return " ".join(f"{x:02x}" for x in b)

def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cur = read_input(sys.argv[1])
    n = len(cur)
    if n not in OK_LENS:
        sys.exit(f"REFUSING: data is {n} bytes (0x{n:x}); known layouts are 114 (7920/7820) and 115 (5820 2.41.0).")
    if not (cur[2:4] == b"\x00\x00" and cur[7] == 0x02 and cur[9] == 0x01):
        sys.exit(f"REFUSING: layout fingerprint mismatch (bytes 2-3={row(cur[2:4])}, b7={cur[7]:02x}, b9={cur[9]:02x}); "
                 "offsets of MmiohBase/MmiohSize cannot be trusted.")
    if cur[0:2] == b"\x00\x02" and cur[4:6] == b"\x04\x00":
        sys.exit("NOTE: MMIOH already set on this machine -- nothing to write.")
    if cur[0:2] != b"\x00\x00" or cur[4:6] != b"\x00\x00":
        sys.exit(f"REFUSING: MmiohBase/MmiohSize are non-zero but not our target ({row(cur[0:2])} / {row(cur[4:6])}); inspect by hand.")

    new = bytearray(cur)
    new[0:2] = b"\x00\x02"   # MmiohBase = 0x0200 (LE) -> 512 GB
    new[4:6] = b"\x04\x00"   # MmiohSize = 0x0004 (LE) -> 256 GB index
    changed = [i for i in range(n) if cur[i] != new[i]]
    assert set(changed) <= {0, 1, 4, 5}

    print(f"data length        : {n} bytes")
    print(f"current  [0:16]    : {row(cur[:16])}")
    print(f"proposed [0:16]    : {row(new[:16])}")
    print(f"bytes changed      : {changed}")
    print(f"bytes 12-13        : {row(cur[12:14])}  (7920: 06 06, 7820: 08 04 -- platform-specific, preserved)")
    payload = new.hex()
    print(f"\n{len(payload)}-char payload : {payload}")

    out = pathlib.Path(sys.argv[0]).resolve().parent / "startup-pass2.nsh"
    out.write_text(
        "@echo -off\n"
        "echo === Sultan Qaboos PASS 2: enable MMIOH window in SocketCommonRcConfig ===\n"
        "echo --- current value ---\n"
        f"dmpstore -guid {GUID_STR} SocketCommonRcConfig\n"
        "echo.\n"
        f"echo Will write {n} bytes; only bytes 0-1 become 00 02 and bytes 4-5 become 04 00.\n"
        "echo First row after the write should read:  00 02 00 00 04 00 "
        + " ".join(f"{x:02X}" for x in new[6:16]) + "\n"
        "echo.\n"
        "echo Press any key to WRITE, or q to quit without writing.\n"
        "pause\n"
        f"setvar SocketCommonRcConfig -guid {GUID_STR} -bs -rt -nv =H{payload}\n"
        "echo --- value after write ---\n"
        f"dmpstore -guid {GUID_STR} SocketCommonRcConfig\n"
        f"dmpstore -guid {GUID_STR} -s fs0:\\rc-after.bin SocketCommonRcConfig\n"
        f"dmpstore -guid {GUID_STR} -s fs1:\\rc-after.bin SocketCommonRcConfig\n"
        "echo.\n"
        "echo If the first row above matches, type:  reset\n"
        "echo Then let it boot STRAIGHT to Windows. Do NOT enter F2 Setup afterwards.\n"
    )
    print(f"\nwrote {out}")

if __name__ == "__main__":
    main()
