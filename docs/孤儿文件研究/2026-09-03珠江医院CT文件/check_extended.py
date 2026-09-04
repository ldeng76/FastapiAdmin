#!/usr/bin/env python3
"""扩展抽样检查。输入 cat|path;输出 cat|path|files|magic|modality。"""
from __future__ import annotations
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_extended_sample.txt")
OUT = Path("/tmp/lnrs_audit/extended_vitality.txt")


def parse_dicom_modality(filepath: Path) -> str:
    try:
        with open(filepath, "rb") as f:
            f.read(128)
            magic = f.read(4)
            if magic != b"DICM":
                return ""
            for _ in range(50):
                hdr = f.read(4)
                if len(hdr) < 4:
                    return ""
                group = int.from_bytes(hdr[0:2], "little")
                elem = int.from_bytes(hdr[2:4], "little")
                vr = f.read(2)
                if vr in (b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"):
                    f.read(2)
                    length = int.from_bytes(f.read(4), "little")
                else:
                    length = int.from_bytes(f.read(2), "little")
                if group == 0x0008 and elem == 0x0060:
                    data = f.read(length)
                    return data.decode("ascii", errors="replace").strip("\x00 ").strip()
                f.seek(length, 1)
                if group > 0x0008:
                    return ""
            return ""
    except Exception:
        return ""


def first_file(d: Path) -> Path | None:
    if not d.is_dir():
        return None
    try:
        with os.scandir(d) as it:
            for ent in it:
                if ent.is_file():
                    return Path(ent.path)
    except Exception:
        return None
    return None


def main() -> int:
    OUT.unlink(missing_ok=True)
    with SAMPLE.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            cat, _, path = line.partition("|")
            d = Path(path)
            files = sum(1 for _ in d.iterdir() if _.is_file()) if d.is_dir() else -1
            first = first_file(d)
            if first is None:
                magic = "no-file"
                modality = ""
            else:
                # 头 132 字节:128 preamble + 4 DICM
                with open(first, "rb") as fp:
                    head132 = fp.read(132)
                magic = "DICM@128" if head132[128:132] == b"DICM" else f"no-dicm"
                modality = parse_dicom_modality(first)
            with OUT.open("a") as g:
                g.write(f"{cat}\tfiles={files}\t{magic}\tmodality={modality or '-'}\t{d}\n")
    print(f"[OK] 写出 {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())