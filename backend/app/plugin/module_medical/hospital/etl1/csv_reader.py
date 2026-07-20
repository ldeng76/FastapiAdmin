"""duckdb 原生 CSV 读取器 (新桥医院 ETL-1 入口)。

2026-07-19: 为陆军军医大学新桥医院 (xinqiao) 数据源新建。原始数据位于
`docs/demodata/01_disk_字段与原始数据_2新桥/`,分两个子目录:
  - 1_5万例排除术后_单一影像号_已处理/  (17 列, 纯 CT)
  - 2_5万例时序影像_带病理_新_待处理/    (30 列, CT + 病理 LEFT JOIN)

设计目标:
- 与 ExcelReader 同接口 (duck-typed), core.run_etl1 可透明切换
- 走 DuckDB 原生 read_csv (优先于 pandas, 已验证对 1GB 量级 CSV 稳定)
- 6 个 CSV 合并为单一 TEMP VIEW, 用 union_by_name=true 防御表头列序差异
- all_varchar=true 把所有列先当字符串入 duckdb, 由 cast_expr_for_type 在
  SheetSpec 层做 TRY_CAST; 这样日期/数字格式异常的列不会让 read_csv 失败

注意事项:
- 不写降级路径; 若遇到 read_csv 不可读的文件再补 pandas 分支
- sheet_name 参数对 CSV 无意义, 但保留以满足接口一致性;
  实际是"哪个子目录"的逻辑名, 调用方传入子目录名 (如 '1_5万例...' 或 '2_5万例...')
- 病理多值字段 (如 `病理.送检时间 = "2025-03-08 08:45:42,2025-03-08 08:46:30"`)
  原样入 parquet, ETL-2 用 string_split + UNNEST 拆开
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from app.core.logger import log

# sheet_name 参数允许中文/点号/斜杠/空格, 与 ExcelReader 同宽白名单
_SHEET_NAME_SAFE_RE = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]+$")


@dataclass(frozen=True)
class SheetView:
    """read_sheet 的返回值: view 名 + 表头列名。

    与 ExcelReader.ShapeView 同 dataclass 定义 (本文件独立定义, 不依赖 excel_reader,
    避免循环 import; 字段完全一致)。
    """

    view_name: str        # duckdb 中已注册的 TEMP VIEW 名
    headers: list[str]    # CSV 表头列名 (按出现顺序)
    sheet_name: str       # 调用方传入的逻辑名 (日志/调试用)


class CsvReader:
    """单目录 CSV 读取器, 内部 glob *.csv union 成单一 TEMP VIEW。

    用法:
        reader = CsvReader('/path/to/csv_subdir')
        reader.ensure_loaded()
        sv = reader.read_sheet('1_5万例排除术后_单一影像号_已处理')
        # sv.view_name 可直接用在 SQL: SELECT ... FROM <sv.view_name>
        # sv.headers 是 CSV 表头列名列表

    设计说明:
        - read_sheet(sheet_name) 接收的是"逻辑表名" (子目录名), 用于日志/缓存键。
          实际 SQL 不依赖此参数, 每次调用重建 TEMP VIEW 指向同一目录 (因目录
          与 sheet_name 一一对应, 调用方约定传入子目录名)。
        - 允许多次 read_sheet 调用同一目录: view 名包含 sheet_name hash, 幂等。
    """

    def __init__(
        self,
        csv_dir: str | Path,
        memory_limit: str = "4GB",
        encoding: str | dict[str, str] | None = None,
    ):
        """初始化 CsvReader。

        参数:
            csv_dir: CSV 目录路径 (子目录或父目录都行, 见 _discover_csvs)
            memory_limit: DuckDB 内存上限
            encoding: 文件编码
                - None: DuckDB 自动检测 (UTF-8 兼容)
                - str: 所有 sheet 统一编码, 如 'gb18030' 用于 GBK 中文 CSV
                - dict: 按 sheet_name 单独指定, 用于多 sheet 编码不一致场景
                  (如新桥: {'SUB1': 'gb18030', 'SUB2': None})
                不指定时, GBK 中文表头会被当乱码导致 DuckDB 回退到 columnNN 占位列名
        """
        p = Path(csv_dir)
        if not p.exists():
            raise FileNotFoundError(f"CSV 目录不存在: {p}")
        if not p.is_dir():
            raise ValueError(f"需要目录路径, 收到文件: {p}")
        self.csv_dir = p.resolve()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._memory_limit = memory_limit
        self._encoding = encoding
        self._loaded = False
        # view 名计数器: 即使 hash 碰撞也保证唯一 (Issue #4)
        self._view_counter = 0

        # 缓存: sheet_name -> glob 出来的 csv 文件列表 (避免每次 read_sheet 重扫)
        self._resolved_csvs: dict[str, list[Path]] = {}

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(":memory:")
            if self._memory_limit:
                self._con.execute(f"PRAGMA memory_limit='{self._memory_limit}';")
        return self._con

    def ensure_loaded(self) -> None:
        """按需加载 DuckDB 扩展。

        - CSV 本身是 duckdb 原生能力, 不需任何扩展
        - 但若指定了非 UTF-8 编码 (如 'gb18030'), 必须装 encodings 扩展
          参考: https://duckdb.org/docs/lts/core_extensions/encodings
          该扩展提供 1000+ 编码, 包括 GBK 系列 (gb18030 / glibc-GBK-2.3.3 / zh_CN.gbk 等)
        """
        if self._loaded:
            return
        if self._encoding:
            try:
                self.con.execute("INSTALL encodings;")
                self.con.execute("LOAD encodings;")
                log.info(
                    "ETL1[CsvReader]: duckdb encodings 扩展已加载 (encoding={})",
                    self._encoding,
                )
            except Exception as e:
                log.error(
                    "ETL1[CsvReader]: 加载 encodings 扩展失败 (网络不可达?): {}", e
                )
                raise
        else:
            log.info("ETL1[CsvReader]: DuckDB 原生 CSV 已就绪 (无需扩展)")
        self._loaded = True

    def _discover_csvs(self, sheet_name: str) -> list[Path]:
        """根据 sheet_name 解析对应的 csv 文件列表。

        解析规则 (2026-07-19 修订):
        1) 若 sheet_name == self.csv_dir.basename → 扫 self.csv_dir
        2) 若 self.csv_dir 下存在 sheet_name 子目录 → 扫该子目录
        3) 否则报错 (不允许"模糊匹配", 防止与错误目录混淆)

        设计动机:
            - xinqiao 的 SheetSpec 同时引用 SUB1 + SUB2 两个子目录
            - run_etl1 只构造一个 CsvReader, 但 SheetSpec 里多个 sheet_name
            - 若 CsvReader 指向"父目录", 可在父目录下找各 sheet_name 对应的子目录
            - 若 CsvReader 指向"子目录本身", 只允许该子目录作为 sheet_name
        """
        if sheet_name in self._resolved_csvs:
            return self._resolved_csvs[sheet_name]

        if self.csv_dir.name == sheet_name:
            csvs = sorted(self.csv_dir.glob("*.csv"))
        else:
            sub = self.csv_dir / sheet_name
            if sub.is_dir():
                csvs = sorted(sub.glob("*.csv"))
            else:
                raise ValueError(
                    f"sheet_name={sheet_name!r} 既不等于当前目录 basename "
                    f"({self.csv_dir.name!r}), 也不是其子目录。"
                    f"传入 CsvReader 的目录必须满足以下任一:\n"
                    f"  (a) 是 sheet_name 对应的子目录本身 (basename == sheet_name), 或\n"
                    f"  (b) 是 sheet_name 对应子目录的父目录"
                )

        if not csvs:
            raise FileNotFoundError(
                f"目录 {self.csv_dir} (sheet_name={sheet_name}) 下未找到任何 .csv 文件"
            )
        self._resolved_csvs[sheet_name] = csvs
        return csvs

    def read_sheet(self, sheet_name: str) -> SheetView:
        """读指定子目录的 CSV 为 duckdb TEMP VIEW。

        幂等: 同一 sheet_name 多次调用会重建 view (CREATE OR REPLACE)。
        view 名保证唯一 (sha256(sheet_name)[:16] + 计数器)。

        安全说明:
        - sheet_name 已过 _SHEET_NAME_SAFE_RE 白名单
        - csv_dir 在构造时 resolve() 过, 来自可信配置
        - read_csv 的 path 不支持 prepared 占位符 (duckdb 1.x 限制),
          必须字面量拼接; 此处把单引号转义后拼接
        """
        if not _SHEET_NAME_SAFE_RE.match(sheet_name):
            raise ValueError(f"非法 sheet_name: {sheet_name!r}")
        self.ensure_loaded()

        csvs = self._discover_csvs(sheet_name)
        if not csvs:
            raise FileNotFoundError(f"sheet_name={sheet_name} 对应目录无 CSV")

        # 字面量拼接 (转义单引号)
        # DuckDB read_csv 支持 glob 列表 (逗号分隔的字面量), 也支持数组 [*]
        # 这里用数组 + list_value 函数避免字符串拼接错误
        path_literals = ", ".join(
            f"'{p.as_posix().replace(chr(39), chr(39) + chr(39))}'" for p in csvs
        )

        # view 名: 全 hash + 递增计数器, 保证无碰撞 (Issue #4)
        self._view_counter += 1
        h = hashlib.sha256(sheet_name.encode("utf-8")).hexdigest()[:16]
        view_name = f"_v_csv_{h}_{self._view_counter}"

        # CREATE OR REPLACE TEMP VIEW, 用 read_csv + union_by_name
        # - all_varchar=true: 所有列先入字符串, 由 SheetSpec 的 cast_expr_for_type 做 TRY_CAST
        # - header=true: 第一行是表头
        # - ignore_errors=true: 单行解析失败不中断 (脏数据安全)
        # - union_by_name=true: 6 个 CSV 表头列序差异时按列名对齐
        # - sample_size=-1: 扫全部行做类型推断 (虽然 all_varchar 已强制, 但仍设)
        # - encoding: 按 sheet_name 解析 (str=统一; dict=按 sheet; None=自动)
        #   GBK 中文 CSV 必须显式指定, 否则 DuckDB 按 UTF-8 解析失败回退 columnNN
        if isinstance(self._encoding, dict):
            enc = self._encoding.get(sheet_name)
        else:
            enc = self._encoding
        encoding_clause = f", encoding='{enc}'" if enc else ""
        self.con.execute(
            f"""
            CREATE OR REPLACE TEMP VIEW {view_name} AS
            SELECT * FROM read_csv(
                [{path_literals}],
                all_varchar=true, header=true,
                ignore_errors=true, union_by_name=true,
                sample_size=-1{encoding_clause}
            )
            """
        )

        # 立即读表头 (LIMIT 0 不拉数据, 仅触发元数据)
        cols = [
            d[0]
            for d in self.con.execute(f"SELECT * FROM {view_name} LIMIT 0").description
        ]

        log.info(
            "ETL1[CsvReader]: 已建 view {} ({} 列, 来自 {} 个 CSV)",
            view_name, len(cols), len(csvs),
        )
        return SheetView(view_name=view_name, headers=cols, sheet_name=sheet_name)

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None