"""duckdb excel 扩展封装 (已验证 4 项可行性)。

可行性结论 (2026-07-19):
- INSTALL excel; LOAD excel; → 0.6s
- 中文 sheet 名 (含点号) 直接支持: sheet='非隐私信息.就诊.病程记录文档'
- all_varchar=true → 所有列 VARCHAR (本文件全是 inline string, 默认就 VARCHAR)
- COPY 大 sheet16 (1.05M 行) to parquet → 28s, 893MB XML → 11.2MB parquet

不写降级路径 (raw zip + iterparse); 若未来遇到不可读文件再补。

2026-07-19 代码评审修复:
- read_sheet 返回 SheetView(view_name, headers), 调用方一次拿到 view 名 + 表头列,
  避免后续 _process_single_sheet/_process_derived 再次 read_xlsx (Issue #1/#5)
- view 名用完整 hash + 计数器保证无碰撞 (Issue #4)
- _MATCH_STRIP 改为函数参数 (normalize_header(..., strip=...)),
  不再用模块级全局开关 (Issue #8)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from app.core.logger import log

# 安全: 与 etl_engine.py 一致的表名白名单, 防 path traversal
# 此处主要用于 sheet_name 的轻度校验 (sheet 名本身允许中文/点号/括号, 故白名单更宽)
_SHEET_NAME_SAFE_RE = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]+$")  # 禁控制字符与 Windows 非法字符


@dataclass(frozen=True)
class SheetView:
    """read_sheet 的返回值: view 名 + 表头列名。

    设计目的: 让调用方 (core._process_single_sheet/_process_derived) 一次拿到
    表头和 view 名, 不必再次 read_xlsx 读 sheet。
    """

    view_name: str        # duckdb 中已注册的 TEMP VIEW 名 (可直接 FROM)
    headers: list[str]    # Excel 表头列名 (按出现顺序)
    sheet_name: str       # 原始 sheet 名 (日志/调试用)


class ExcelReader:
    """单文件 Excel 读取器, 复用同一个 duckdb 连接。

    用法:
        reader = ExcelReader(xlsx_path)
        reader.ensure_loaded()
        sv = reader.read_sheet("非隐私信息.患者基本信息")
        # sv.view_name 可直接用在 SQL: SELECT ... FROM <sv.view_name>
        # sv.headers 是 Excel 表头列名列表
    """

    def __init__(self, xlsx_path: str | Path, memory_limit: str = "4GB"):
        p = Path(xlsx_path)
        if not p.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {p}")
        if p.suffix.lower() != ".xlsx":
            raise ValueError(f"仅支持 .xlsx, 收到: {p.suffix}")
        self.xlsx_path = p.resolve()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._memory_limit = memory_limit
        self._loaded = False
        # view 名计数器: 即使 hash 碰撞也保证唯一 (Issue #4)
        self._view_counter = 0

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(":memory:")
            if self._memory_limit:
                self._con.execute(f"PRAGMA memory_limit='{self._memory_limit}';")
        return self._con

    def ensure_loaded(self) -> None:
        """幂等地 INSTALL + LOAD excel 扩展。"""
        if self._loaded:
            return
        try:
            self.con.execute("INSTALL excel;")
            self.con.execute("LOAD excel;")
            self._loaded = True
            log.info("ETL1: duckdb excel 扩展已加载")
        except Exception as e:
            log.error("ETL1: 加载 excel 扩展失败 (网络不可达?): {}", e)
            raise

    def list_sheets(self) -> list[str]:
        """列出所有 sheet 名 (用 zipfile 读 workbook.xml, 不依赖 duckdb)。

        duckdb excel 扩展不暴露 sheet_names 表函数, 用 Python 直接读 OOXML。
        """
        import zipfile
        import xml.etree.ElementTree as ET

        NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with zipfile.ZipFile(self.xlsx_path) as z:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            return [sh.attrib["name"] for sh in wb.findall(".//main:sheet", NS)]

    def read_sheet(self, sheet_name: str) -> SheetView:
        """读单 sheet 为 duckdb TEMP VIEW, 并返回 view 名 + 表头列名。

        幂等: 同一 sheet 多次调用会重建 view (CREATE OR REPLACE)。
        view 名保证唯一 (hash + 计数器), 无碰撞风险。

        安全说明:
        - sheet_name 已在调用前过 _SHEET_NAME_SAFE_RE 白名单
        - xlsx_path 在构造时 resolve() 过, 来自可信配置
        - read_xlsx 的 path/sheet 不支持 prepared 占位符 (duckdb 1.5 限制),
          必须字面量拼接; 此处把单引号转义后拼接
        """
        if not _SHEET_NAME_SAFE_RE.match(sheet_name):
            raise ValueError(f"非法 sheet 名: {sheet_name!r}")
        self.ensure_loaded()

        # 字面量拼接 (转义单引号)
        path_lit = self.xlsx_path.as_posix().replace("'", "''")
        sheet_lit = sheet_name.replace("'", "''")

        # view 名: 全 hash + 递增计数器, 保证无碰撞 (Issue #4)
        # hash() 在 Python 3 默认 random salt, 进程内稳定
        self._view_counter += 1
        # 用 sha256 前 16 hex 而不是 Python 内置 hash, 避免跨进程不一致 (调试日志可读)
        import hashlib
        h = hashlib.sha256(sheet_name.encode("utf-8")).hexdigest()[:16]
        view_name = f"_v_read_{h}_{self._view_counter}"

        self.con.execute(
            f"""
            CREATE OR REPLACE TEMP VIEW {view_name} AS
            SELECT * FROM read_xlsx('{path_lit}', sheet='{sheet_lit}',
                                     all_varchar=true, header=true, ignore_errors=true)
            """
        )
        # 立即读表头 (LIMIT 0 不拉数据, 仅触发元数据)
        cols = [
            d[0]
            for d in self.con.execute(f"SELECT * FROM {view_name} LIMIT 0").description
        ]
        return SheetView(view_name=view_name, headers=cols, sheet_name=sheet_name)

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None


# ---------------- 列名匹配 helper ----------------

def normalize_header(h: str, strip: bool = True) -> str:
    """规范化 Excel 表头用于匹配。

    strip=True (默认): 去掉首尾空白。
    探索发现 '非隐私信息.就诊.就诊基本信息.医疗付款方式 ' 有尾随空格,
    因此 src 匹配前必须 strip。但保留内部空白 (中文表头里可能有合法空格)。

    2026-07-19 修复 (Issue #8): strip 改为参数, 不再依赖模块级全局 _MATCH_STRIP。
    """
    if not isinstance(h, str):
        return h
    return h.strip() if strip else h


def build_column_map(
    excel_headers: list[str],
    wanted_src: list[str],
    strip: bool = True,
) -> dict[str, str]:
    """建立 src (wanted) → 实际 Excel 列名 的映射。

    匹配规则: wanted 里的每个 src 名, 在 excel_headers 里找 strip() 后相等的。
    若找不到, 该 src 缺失 (调用方决定是 required 报错还是 default)。

    返回: {wanted_src: excel_header}, 缺失的 src 不在返回 dict 里。
    """
    excel_norm: dict[str, str] = {}
    for h in excel_headers:
        if h is None:
            continue
        nh = normalize_header(h, strip=strip)
        # 若有重名列, 后者覆盖前者 (Excel 一般无重名, 不深究)
        excel_norm[nh] = h

    result: dict[str, str] = {}
    for want in wanted_src:
        nwant = normalize_header(want, strip=strip)
        if nwant in excel_norm:
            result[want] = excel_norm[nwant]
    return result
