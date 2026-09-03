#!/usr/bin/env python3
"""抽样检查孤儿 Study 目录的存活性 + DICOM Modality。

输入:/tmp/lnrs_audit/orphan_non_ymd_sample.txt (格式: cat|path)
输出:/tmp/lnrs_audit/non_ymd_vitality.txt (TSV)
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_non_ymd_sample.txt")
OUT = Path("/tmp/lnrs_audit/non_ymd_vitality.txt")


def parse_dicom_modality(filepath: Path) -> str:
    """裸解析:从 DICM magic 后 explicit VR little endian 读 (0008,0060) Modality。

    DICOM 标准:文件以 128 字节 preamble + "DICM" 开始,然后按 explicit VR little endian
    走;modality tag 是 (0008,0060),VR='CS',长度 2 字节。
    返回 'CT'/'MR'/.../''。
    """
    try:
        with open(filepath, "rb") as f:
            preamble = f.read(128)
            magic = f.read(4)
            if magic != b"DICM":
                return ""
            # 解析数据元素直到找到 (0008,0060)
            seen_0008 = False
            for _ in range(50):  # 最多看 50 个元素
                hdr = f.read(4)
                if len(hdr) < 4:
                    return ""
                group = int.from_bytes(hdr[0:2], "little")
                elem = int.from_bytes(hdr[2:4], "little")
                # VR 2 字节;对 OB/OW/OF/SQ/UT/UN 显式 VR,长度前还有 2 字节保留
                vr = f.read(2)
                if vr in (b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"):
                    f.read(2)  # 保留
                    length = int.from_bytes(f.read(4), "little")
                else:
                    length = int.from_bytes(f.read(2), "little")
                if group == 0x0008 and elem == 0x0060:
                    data = f.read(length)
                    return data.decode("ascii", errors="replace").strip("\x00 ").strip()
                # 跳过此元素
                f.seek(length, 1)
                if group > 0x0008:
                    return ""  # 已超过 modality tag 所在 group
            return ""
    except Exception:
        return ""


def first_file(d: Path) -> Path | None:
    """取目录内第一个文件(任意名字)。"""
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
                with open(first, "rb") as fp:
                    head128 = fp.read(128)
                magic = "DICM" if b"DICM" in head128 else f"first16={head128[:16]!r}"
                modality = parse_dicom_modality(first)
            with OUT.open("a") as g:
                g.write(f"{cat}\t{d}\tfiles={files}\tmagic={magic}\tmodality={modality or '-'}\n")
    print(f"[OK] 写出 {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())