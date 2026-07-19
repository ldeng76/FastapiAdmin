"""center 配置包。

import 此包会自动注册所有 centers/*.py 里的 CenterConfig。
新增医院只需加一份 <code>.py 并在此 import。
"""

from __future__ import annotations

# 触发 register_center 副作用
from . import shengyi as _shengyi  # noqa: F401
from . import zhujiang as _zhujiang  # noqa: F401

__all__ = ["shengyi", "zhujiang"]
