#!/usr/bin/env python3
"""通用抽样检查脚本:接受 cat|path 格式,输出 cat|path|files|magic|modality。"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import sys
sys.path.insert(0, "/tmp/lnrs_audit")
# 复用前脚本的解析逻辑
exec(open("/tmp/lnrs_audit/check_vitality.py").read().replace("SAMPLE = Path(\"/tmp/lnrs_audit/orphan_non_ymd_sample.txt\")", "SAMPLE = Path(\"/tmp/lnrs_audit/orphan_extended_sample.txt\")").replace("non_ymd_vitality.txt", "extended_vitality.txt"))