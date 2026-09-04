#!/usr/bin/env python3
"""对真孤儿抽样读 Modality。"""
from __future__ import annotations
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_v4_sample.txt")
OUT = Path("/tmp/lnrs_audit/v4_modality.txt")


def parse_dicom_modality(filepath: Path) -> str:
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
                return f.read(length).decode("ascii", errors="replace").strip("\x00 ").strip()
            f.seek(length, 1)
            if group > 0x0008:
                return ""
    return ""


def first_file(d: Path):
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
    n_total = n_no_file = n_no_dicm = n_other = 0
    mod_counter = {}
    with SAMPLE.open() as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line.strip(): continue
            cat, _, path = line.partition("|")
            d = Path(path)
            n_total += 1
            first = first_file(d)
            if first is None:
                n_no_file += 1
                modality = "NOFILE"
            else:
                with open(first, "rb") as fp:
                    head132 = fp.read(132)
                if head132[128:132] != b"DICM":
                    n_no_dicm += 1
                    modality = "NODICM"
                else:
                    modality = parse_dicom_modality(first) or "?"
                    if modality not in ("CT","MR","XR","US","PET","NM","Pathology","Genetic","Other"):
                        n_other += 1
            mod_counter[modality] = mod_counter.get(modality, 0) + 1
            if (i+1) % 500 == 0:
                print(f"[{i+1}] {path} → {modality}", file=sys.stderr)
    with OUT.open("w") as g:
        g.write(f"# 总抽样: {n_total}\n")
        g.write(f"# 无文件: {n_no_file}\n")
        g.write(f"# 无 DICM: {n_no_dicm}\n")
        g.write(f"# 不在标准 9 种 modality 中: {n_other}\n")
        g.write(f"# Modality 分布:\n")
        for m, c in sorted(mod_counter.items(), key=lambda x: -x[1]):
            g.write(f"  {m}: {c}\n")
    print(f"[OK] 写出 {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())