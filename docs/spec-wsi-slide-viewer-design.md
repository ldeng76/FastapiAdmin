# WSI 病理切片（svs）放大浏览 · 后端方案设计

> **日期**：2026-08-05
> **状态**：设计稿，待审核
> **作者**：dzy
> **审核要点**：本方案以「动态切片 + Deep Zoom (DZI) 协议 + OpenSeadragon」为推荐起步组合，请重点审核第四节（架构）、第六节（API 与 service）、第十一节（风险）。
> **真实样本**：`D:\wkdats\2026\07\301\WSI_sample\B1229048-2.svs`（2.7 GB，Aperio SVS / BigTIFF）

---

## 0. TL;DR

svs 文件本身就是「金字塔 + 分块 JPEG」的瓦片结构，**放大浏览不需要重新发明算法**，只要把 svs 内部的瓦片翻译成前端查看器能消费的标准协议即可——和地图（Leaflet/Google Maps）放大完全同一套思路。

本方案核心是「**OpenSlide 解码 svs + Deep Zoom 协议暴露金字塔 + OpenSeadragon 前端按视口拉瓦片**」：

- **后端**：新建 `module_medical/slide` 插件（与现有 `module_medical/dicom` 平行），用 OpenSlide 实时读取 svs 的指定区域，按 Deep Zoom 标准（DZI）暴露瓦片。
- **前端**：新增 OpenSeadragon 查看器，只渲染视口内可见瓦片，平移/缩放时逐级清晰。
- **分阶段**：P0 动态切片跑通闭环（1~2 天），P2 演进到离线静态瓦片（生产高并发）。

---

## 1. 背景与目标

### 1.1 需求

- 在页面上展示真实的 svs 格式病理切片。
- 先显示缩略图，用户选择某区域放大时，按需从后台取该区域更高分辨率的瓦片，逐级清晰。
- 体验类比地图放大（Leaflet / Google Maps 的 slippy map）。

### 1.2 现状（基于代码调研）

| 项 | 结论 | 证据 |
|---|---|---|
| 现有影像能力 | **仅 DICOM（CT 切片），无 WSI/切片能力** | `module_medical/dicom/`，前端 cornerstone3D（`DicomViewer.vue`） |
| 后端框架 | FastAPI 插件式动态路由，`module_*` 自动挂载 | `app/core/discover.py`，全局前缀 `/api/v1` |
| 配置体系 | Pydantic-Settings + `.env.{ENV}`，已有 `DICOM_DATA_DIR` 范例 | `setting.py:237` |
| Python 影像库 | **未安装** openslide / tifffile / Pillow / numpy | 当前解释器实测 `ModuleNotFoundError` |
| 前端瓦片库 | **未安装** OpenSeadragon | `package.json` 仅有 cornerstonejs |
| 样本文件 | 2.7 GB Aperio SVS / BigTIFF（magic `49 49 2B 00`） | 文件头十六进制 |

**关键结论**：cornerstone3D 是为 DICOM 切片栈设计的，不适合 WSI 金字塔场景；WSI 必须另起一套瓦片查看器。

### 1.3 非目标

- 不在本文档范围内：切片上传入库流水线、AI 标注/ROI、多切片对比视图、患者详情页的菜单/权限接入细节（沿用现有 `module_medical:slide:*` 权限点即可）。
- 不重写 DICOM 阅片路径。

---

## 2. 名词约定

| 术语 | 含义 |
|---|---|
| **WSI** | Whole Slide Image，整片病理切片数字图像 |
| **svs** | Aperio 公司的 WSI 格式，本质是 BigTIFF，内含金字塔 + 关联图（缩略图/标签） |
| **金字塔（Pyramid）** | 同一张图的多级降采样副本，level 0 = 原始分辨率，越往上越小，用于不同缩放级别快速取图 |
| **瓦片（Tile）** | 把每一层切成固定大小（通常 256×256）的小块，按 (level, col, row) 索引 |
| **DZI** | Deep Zoom Image，微软提出的金字塔瓦片描述协议（一个 `.dzi` XML + `_files/{L}/{C}_{R}.jpg`） |
| **IIIF** | International Image Interoperability Framework，学术/博物馆行业的图像互操作标准 |
| **OpenSlide** | C 库 + Python 绑定，统一读取 svs/ndpi/tiff 等多种 WSI 格式 |
| **OpenSeadragon** | JavaScript 瓦片查看器，事实标准，原生支持 DZI/IIIF |

---

## 3. 选型说明

### 3.1 切片策略：动态切片（起步）→ 离线切片（生产）

| 维度 | 动态切片 | 离线切片 |
|---|---|---|
| 工作方式 | 每次瓦片请求实时 `read_region` | 上传时用 `vips dzsave` 预生成 DZI 目录，FastAPI `StaticFiles` 托管 |
| 首次延迟 | 即放即看 | 需预处理（2.7 GB 约几分钟） |
| 运行时 CPU | 随并发上升 | 零 CPU（纯静态） |
| 磁盘 | 仅原图 | 多占 ~1.1~1.3× |
| 适用 | 开发 / PoC / 中小规模 | 生产 / 高并发 |

**本方案 P0 采用动态切片**，P2 演进到离线切片。两者协议层（DZI）完全一致，前端代码零改动即可切换。

### 3.2 瓦片协议：Deep Zoom (DZI)

候选有 DZI / IIIF / 自定义三种。**选 DZI**：结构最简单（一个 XML + 平铺 JPEG），OpenSeadragon 一行 `tileSources` 即可加载，实现成本最低。IIIF 留作 P3 多源互操作时再加（仅改协议层，OpenSlide 句柄复用）。

### 3.3 前端查看器：OpenSeadragon

数字病理学/Web 显微镜的事实标准，轻量（~150 KB），原生 DZI/IIIF，平滑缩放/平移内建。不沿用 cornerstone3D（其设计目标是 DICOM 切片栈，非 WSI 金字塔）。

---

## 4. 总体架构

```
┌─────────────────────────────┐      ┌──────────────────────────────┐
│  前端 OpenSeadragon          │      │  后端 FastAPI plugin          │
│  (WsiViewer.vue)            │      │  module_medical/slide/        │
│                             │ HTTP │                              │
│  tileSources: .dzi XML ─────┼──────┼─▶ GET /medical/slide/{id}.dzi │
│                             │      │     → 金字塔元信息 XML        │
│  动态按视口拉瓦片 ───────────┼──────┼─▶ GET /medical/slide/{id}_    │
│  (level/col_row.jpg)        │      │     files/{L}/{C}_{R}.jpg     │
│                             │      │     → OpenSlide read_region   │
│  缩略图 <img> ──────────────┼──────┼─▶ GET /medical/slide/{id}/    │
│                             │      │     thumbnail                 │
└─────────────────────────────┘      └──────────────────────────────┘
                                                    │
                            ┌───────────────────────┴───────────────┐
                            │  WSI_DATA_DIR (配置项)                │
                            │  B1229048-2.svs  ← OpenSlide 直读     │
                            └───────────────────────────────────────┘
```

**「像地图放大」的实现原理**：
1. OpenSeadragon 启动时先请求 `.dzi` XML，解析出金字塔层数、每层尺寸、瓦片大小。
2. 用户当前视口对应金字塔某一层的一组 (col, row) 瓦片，OpenSeadragon 只请求这些瓦片。
3. 用户放大 → 视口对应更高 level（更高分辨率）的瓦片，OpenSeadragon 自动请求覆盖旧区域 → 逐级清晰。
4. 后端 `get_tile(level, col, row)` 调用 OpenSlide `read_region` 从 svs 内部金字塔解码出该瓦片 → 编码 JPEG 返回。

后端不需要自己实现放大动画/平滑过渡，这些全部由 OpenSeadragon 内建。

---

## 5. 依赖与环境

### 5.1 后端 Python 依赖（追加到 `backend/requirements.txt`）

```
openslide-python>=1.3.1
Pillow>=10.0.0
numpy>=1.26.0
```

### 5.2 OpenSlide 二进制（关键，Windows 必须处理）

OpenSlide 是 C 库，Python 绑定需找到 native DLL。Windows 下必须额外安装：

- **方案 A（推荐，通用）**：下载 [OpenSlide Windows binaries](https://openslide.org/download/) 解压，通过配置项 `OPENSLIDE_PATH` 指向其 `bin` 目录，代码里 `os.add_dll_directory(...)` 显式加载（见 7.2）。
- **方案 B（conda 用户）**：`conda install -c conda-forge openslide`，conda 自动带 DLL。
- **Linux/Docker**：`apt install -y python3-openslide openslide-tools`。

### 5.3 前端依赖（追加到 `frontend/web/package.json`）

```json
"openseadragon": "^4.1.1"
```

---

## 6. 配置项（融入现有 `setting.py` 风格）

仿照 `DICOM_DATA_DIR`（`setting.py:237`）的写法，在 DICOM 配置块下方新增 WSI 配置块：

```python
# ================================================= #
# ************** WSI 病理切片数据配置 ************** #
# ================================================= #
# WSI 数据根目录（svs/ndpi/tiff 等），文件即放即看（动态切片）。
# dev 默认指向示例数据；生产通过 .env 覆盖。
WSI_DATA_DIR: Path = BASE_DIR.parent / "docs" / "wsi_demo"
# OpenSlide DLL 路径（Windows 必填；Linux/Mac 可留空走系统库）。
OPENSLIDE_PATH: str = ""
# 动态切片瓦片 LRU 缓存上限（按瓦片张数），生产建议调大。
WSI_TILE_CACHE_SIZE: int = 512
# 离线切片产物目录（DZI 瓦片，StaticFiles 托管；留空表示不启用离线切片）。
WSI_DZI_OUTPUT_DIR: Path = BASE_DIR.parent / "docs" / "wsi_dzi"
# 单瓦片像素（Deep Zoom 标准固定 256，勿改）。
WSI_TILE_SIZE: int = 256
# 瓦片重叠像素（OpenSeadragon 默认 0 即可）。
WSI_TILE_OVERLAP: int = 0
```

`.env.h125`（或对应环境）覆盖示例：

```
WSI_DATA_DIR=D:/wkdats/2026/07/301/WSI_sample
OPENSLIDE_PATH=C:/openslide/bin
```

---

## 7. 后端实现

### 7.1 目录结构（新建插件，自动挂到 `/medical`）

按 `app/core/discover.py` 的发现规则，`module_medical/slide/controller.py` 顶层定义的 `APIRouter` 会自动挂到容器前缀 `/medical`，叠加全局 `/api/v1` 后对外是 `/api/v1/medical/slide/...`。

```
backend/app/plugin/module_medical/slide/
├── __init__.py
├── controller.py    # DZI 协议路由（业务接口 + 协议接口）
├── service.py       # OpenSlide 封装 + 瓦片渲染 + 三层缓存
├── repository.py    # 目录扫描 + 文件索引（仿 dicom/repository.py）
└── dz.py            # Deep Zoom 坐标换算（纯函数）
```

### 7.2 `service.py`（OpenSlide 封装，核心放大实现）

三层缓存设计是性能关键：

1. **切片句柄缓存**（进程级）：OpenSlide 打开 2.7 GB 文件是 mmap，重开代价高，必须缓存。
2. **DZI 元信息缓存**：金字塔结构不变，按 slide_id 缓存 XML。
3. **瓦片 LRU 缓存**：同一 (slide_id, level, col, row) 的 JPEG bytes 缓存。

```python
"""WSI 切片服务：封装 OpenSlide，提供 Deep Zoom 兼容的瓦片访问。"""
import os
import math
from io import BytesIO
from functools import lru_cache
from threading import Lock

from PIL import Image

from app.config.setting import settings
from . import repository


# ----- 0. Windows 下显式加载 OpenSlide DLL（必须在 import openslide 之前） -----
_dll_loaded = False
_dll_lock = Lock()

def _ensure_openslide_dll() -> None:
    global _dll_loaded
    if _dll_loaded:
        return
    with _dll_lock:
        if _dll_loaded:
            return
        path = settings.OPENSLIDE_PATH
        if path and os.name == "nt":
            # os.add_dll_directory 是 Py3.8+ 加载非系统 DLL 的正规方式
            os.add_dll_directory(path)
        _dll_loaded = True

_ensure_openslide_dll()
import openslide  # noqa: E402


class SlideOutOfRange(Exception):
    """请求的瓦片 (level, col, row) 超出金字塔范围。"""


# ----- 1. 切片句柄缓存（进程级 LRU） -----
_slide_cache: dict[str, openslide.OpenSlide] = {}
_slide_lock = Lock()

def _get_slide(slide_id: str) -> openslide.OpenSlide:
    if slide_id not in _slide_cache:
        with _slide_lock:
            if slide_id not in _slide_cache:
                path = repository.find_slide_path(slide_id)
                if path is None:
                    raise FileNotFoundError(slide_id)
                slide = openslide.OpenSlide(str(path))
                # LRU 上限保护：超出则淘汰最早一条
                if len(_slide_cache) >= 64:  # 句柄数上限，按机器内存调
                    _slide_cache.pop(next(iter(_slide_cache)))
                _slide_cache[slide_id] = slide
    return _slide_cache[slide_id]


# ----- 2. DZI 级别换算（Deep Zoom ↔ OpenSlide 坐标系） -----
# Deep Zoom 约定：level 0 = 1×1 像素，level 递增 ×2，max_level 使 2^max >= max(w,h)
# OpenSlide 约定：level_dimensions[0] = 最大基底（原始分辨率）
def _max_level(base_w: int, base_h: int) -> int:
    return int(math.ceil(math.log2(max(base_w, base_h))))


def get_dzi_xml(slide_id: str) -> tuple[str, str]:
    """返回 (DZI XML, ETag)。金字塔结构不变，可长期缓存。"""
    slide = _get_slide(slide_id)
    w, h = slide.dimensions
    tile = settings.WSI_TILE_SIZE
    overlap = settings.WSI_TILE_OVERLAP
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Image TileSize="{tile}" Overlap="{overlap}" Format="jpeg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        f'<Size Width="{w}" Height="{h}"/></Image>'
    )
    return xml, f'"{slide_id}-dzi"'


# ----- 3. 瓦片渲染（核心：把 DZI 的 level/col/row 翻译成 OpenSlide read_region） -----
@lru_cache(maxsize=settings.WSI_TILE_CACHE_SIZE)
def _render_tile(slide_id: str, level: int, col: int, row: int) -> bytes:
    slide = _get_slide(slide_id)
    tile = settings.WSI_TILE_SIZE
    base_w, base_h = slide.dimensions
    max_lvl = _max_level(base_w, base_h)

    # 该 DZI level 在 level_0 上的缩放比
    scale = 2 ** (level - max_lvl)
    layer_w = int(math.ceil(base_w * scale))
    layer_h = int(math.ceil(base_h * scale))

    # 瓦片越界检查
    x, y = col * tile, row * tile
    if x >= layer_w or y >= layer_h:
        raise SlideOutOfRange

    # 策略：复用 svs 内置金字塔——选 OpenSlide 自带 level 中分辨率刚好 >= 该层的，
    #       从它 read_region 到 tile×tile，再 resize 到标准 tile 输出。
    #       这样既快（不每次从 level_0 全解），又统一输出尺寸。
    target_level0_w = tile / scale  # 这个 tile 覆盖的 level_0 像素范围
    os_level = 0
    for i, (lw, _lh) in enumerate(slide.level_dimensions):
        if lw >= target_level0_w:
            os_level = i
            break
    region_loc0 = (int(col * tile / scale), int(row * tile / scale))
    img = slide.read_region(region_loc0, os_level, (tile, tile))

    # read_region 返回 RGBA，转 RGB 存 JPEG（体积小 3~5 倍）
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    buf = BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def get_tile(slide_id: str, level: int, col: int, row: int) -> tuple[bytes, str]:
    data = _render_tile(slide_id, level, col, row)
    return data, f'"{slide_id}-{level}-{col}-{row}"'


# ----- 4. 缩略图 / 标签图 -----
def get_thumbnail(slide_id: str, viewport: str | None = None) -> bytes:
    """优先用 svs 内置 associated image 'thumbnail'，否则降采样最底层。"""
    slide = _get_slide(slide_id)
    w, h = (256, 256)
    if viewport:
        try:
            parts = [int(p) for p in viewport.split(",")]
            if len(parts) == 2:
                w, h = parts
        except ValueError:
            pass
    try:
        thumb = slide.associated_images["thumbnail"]
    except KeyError:
        # 降采样：用 OpenSlide get_thumbnail（内部走最佳 level）
        thumb = slide.get_thumbnail((w, h))
    thumb = thumb.convert("RGB")
    # 归一到请求尺寸
    if thumb.size != (w, h):
        thumb = thumb.resize((w, h), Image.LANCZOS)
    buf = BytesIO()
    thumb.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def get_associated_image(slide_id: str, name: str = "label") -> bytes:
    """获取 svs 关联图（label/macro），不存在则 404。"""
    slide = _get_slide(slide_id)
    img = slide.associated_images.get(name)
    if img is None:
        raise KeyError(name)
    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


def get_slide_info(slide_id: str) -> dict | None:
    """切片元信息（供列表/详情页展示）。"""
    path = repository.find_slide_path(slide_id)
    if path is None:
        return None
    slide = _get_slide(slide_id)
    return {
        "id": slide_id,
        "filename": path.name,
        "vendor": slide.vendor,
        "base_width": slide.dimensions[0],
        "base_height": slide.dimensions[1],
        "level_count": slide.level_count,
        "level_downsamples": [round(d, 4) for d in slide.level_downsamples],
        "mpp_x": slide.properties.get(openslide.PROPERTY_NAME_MPP_X),
        "mpp_y": slide.properties.get(openslide.PROPERTY_NAME_MPP_Y),
        "objective_power": slide.properties.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER),
        "associated_images": list(slide.associated_images.keys()),
    }
```

### 7.3 `controller.py`（路由，对齐 `dicom/controller.py` 风格）

两类路由分离：业务接口（列表/元信息）记日志 + 统一返回；协议接口（DZI/瓦片）裸返回，避免每瓦片一条日志。

```python
"""WSI 病理切片控制器（Deep Zoom 协议，供 OpenSeadragon 使用）。

与 module_medical/dicom/controller.py 的取舍一致：
- 大量瓦片二进制路由不使用 OperationLogRoute（避免日志爆炸）
- 列表/元信息等业务接口走 SuccessResponse + OperationLogRoute
"""
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, HTTPException
from fastapi.responses import Response as RawResponse

from app.common.response import SuccessResponse  # 按项目实际 import 路径调整
from app.core.router_class import OperationLogRoute  # 同上
from .service import SlideService, SlideOutOfRange

# ----- 业务接口：列表/元信息（记日志 + 统一返回） -----
SlideRouter = APIRouter(prefix="/slide", route_class=OperationLogRoute, tags=["病理切片"])

# ----- 协议接口：DZI/瓦片（裸返回，不记日志） -----
# 注意：prefix 与业务 router 一致，最后 include 进 SlideRouter 对外统一
DziRouter = APIRouter(prefix="/slide")


@SlideRouter.get("", summary="列出所有切片")
async def list_slides():
    return SuccessResponse(data=SlideService.list_slides())


@SlideRouter.get("/{slide_id}", summary="切片元信息")
async def get_slide(
    slide_id: Annotated[str, Path(description="切片 id（文件名去扩展名）")],
):
    info = SlideService.get_slide_info(slide_id)
    if info is None:
        raise HTTPException(404, "切片不存在")
    return SuccessResponse(data=info)


@DziRouter.get("/{slide_id}.dzi", summary="Deep Zoom 描述文件")
async def get_dzi(
    slide_id: Annotated[str, Path(description="切片 id")],
):
    """OpenSeadragon 首先请求它解析金字塔结构。"""
    try:
        xml, etag = SlideService.get_dzi_xml(slide_id)
    except FileNotFoundError:
        raise HTTPException(404, "切片不存在")
    return RawResponse(
        content=xml,
        media_type="text/xml",
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )


@DziRouter.get(
    "/{slide_id}_files/{level}/{col}_{row}.jpg",
    summary="Deep Zoom 瓦片",
)
async def get_tile(
    slide_id: Annotated[str, Path(description="切片 id")],
    level: Annotated[int, Path(description="金字塔层级，0=最小")],
    col: Annotated[int, Path(ge=0, description="瓦片列号")],
    row: Annotated[int, Path(ge=0, description="瓦片行号")],
):
    """按 (level, col, row) 返回单个瓦片 JPEG。核心放大接口。"""
    try:
        img_bytes, etag = SlideService.get_tile(slide_id, level, col, row)
    except FileNotFoundError:
        raise HTTPException(404, "切片不存在")
    except SlideOutOfRange:
        raise HTTPException(404, "瓦片越界")
    return RawResponse(
        content=img_bytes,
        media_type="image/jpeg",
        # 瓦片内容永不变，可一年强缓存
        headers={"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"},
    )


@DziRouter.get("/{slide_id}/thumbnail", summary="缩略图")
async def get_thumbnail(
    slide_id: Annotated[str, Path(description="切片 id")],
    viewport: Annotated[str | None, Query(description="尺寸，如 256,256")] = None,
):
    try:
        img_bytes = SlideService.get_thumbnail(slide_id, viewport=viewport)
    except FileNotFoundError:
        raise HTTPException(404, "切片不存在")
    return RawResponse(content=img_bytes, media_type="image/jpeg")


@DziRouter.get("/{slide_id}/associated/{name}", summary="关联图（label/macro）")
async def get_associated(
    slide_id: Annotated[str, Path(description="切片 id")],
    name: Annotated[str, Path(description="关联图名称，如 label/macro")],
):
    try:
        img_bytes = SlideService.get_associated_image(slide_id, name)
    except FileNotFoundError:
        raise HTTPException(404, "切片不存在")
    except KeyError:
        raise HTTPException(404, f"关联图 {name} 不存在")
    return RawResponse(content=img_bytes, media_type="image/jpeg")


# 把协议路由挂到业务 router 下（对外只暴露 SlideRouter）
SlideRouter.include_router(DziRouter)
```

### 7.4 `repository.py`（目录扫描 + 路径防穿越，仿 `dicom/repository.py`）

```python
"""WSI 切片目录扫描与索引（仿 module_medical/dicom/repository.py 的轻量设计）。

与 DICOM 一样：切片数据不入库，OpenSlide 直读本地文件。
"""
from pathlib import Path

from app.config.setting import settings

SUPPORTED_EXT = {".svs", ".ndpi", ".tif", ".tiff", ".vsi", ".scn", ".mrxs"}


def list_slide_ids() -> list[str]:
    """列出 WSI_DATA_DIR 下所有受支持格式的切片 id（文件名去扩展名）。"""
    root = settings.WSI_DATA_DIR
    if not root.exists():
        return []
    return sorted(
        p.stem for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )


def find_slide_path(slide_id: str) -> Path | None:
    """按 slide_id 定位文件。防穿越：slide_id 必须是纯文件名。"""
    if not slide_id or "/" in slide_id or "\\" in slide_id or ".." in slide_id:
        return None
    for ext in SUPPORTED_EXT:
        candidate = settings.WSI_DATA_DIR / f"{slide_id}{ext}"
        # resolve + is_relative_to 双保险
        if candidate.exists():
            resolved = candidate.resolve()
            if resolved.is_relative_to(settings.WSI_DATA_DIR.resolve()):
                return resolved
    return None
```

> 安全：路径校验必须做，与 `module_common/file/service.py:_validate_download_path` 同一原则，防止 `../../etc/passwd` 类穿越。

---

## 8. 前端实现

### 8.1 安装依赖

```bash
cd frontend/web && pnpm add openseadragon
```

### 8.2 API 客户端 `src/api/module_medical/slide.ts`（新建，仿 `dicom.ts`）

```ts
import request from "@/utils/request"; // 按项目实际 import 调整

export interface SlideInfo {
  id: string;
  filename: string;
  vendor: string;
  base_width: number;
  base_height: number;
  level_count: number;
  mpp_x: string | null;
  mpp_y: string | null;
  objective_power: string | null;
  associated_images: string[];
}

export const WsiAPI = {
  list()       : GET    /medical/slide            → SlideInfo[]
  detail(id)   : GET    /medical/slide/{id}       → SlideInfo
  // tileSources 直接给 OpenSeadragon 用字符串，不走 axios
  dziUrl(id)   : `${apiBase}/medical/slide/${id}.dzi`
  tileUrl(id)  : `${apiBase}/medical/slide/${id}_files/{level}/{col}_{row}.jpg`
  thumbnail(id): `${apiBase}/medical/slide/${id}/thumbnail`
};
```

### 8.3 查看器组件 `views/module_medical/patient/components/WsiViewer.vue`（新建）

```vue
<template>
  <div class="wsi-viewer">
    <div ref="viewerEl" class="osd-container"></div>
    <div class="wsi-toolbar">
      <span class="zoom-label">{{ zoomLabel }}</span>
      <el-button size="small" @click="goHome">复位</el-button>
      <el-button size="small" @click="zoomBy(2)">放大</el-button>
      <el-button size="small" @click="zoomBy(0.5)">缩小</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import OpenSeadragon from "openseadragon";

const props = defineProps<{ slideId: string }>();
const viewerEl = ref<HTMLElement>();
const zoomLabel = ref("1×");
let viewer: OpenSeadragon.Viewer | null = null;

const apiBase = import.meta.env.VITE_APP_BASE_API || "/api/v1";

function buildViewer() {
  if (!viewerEl.value) return;
  viewer = OpenSeadragon({
    element: viewerEl.value,
    // 关键：tileSources 直接指向后端 DZI XML，OSD 自动解析并按视口请求瓦片
    tileSources: `${apiBase}/medical/slide/${props.slideId}.dzi`,
    prefixUrl: "https://cdn.jsdelivr.net/npm/openseadragon@4.1.1/build/openseadragon/images/",
    showNavigationControl: false,
    maxZoomPixelRatio: 1.0,       // 不放大超过原始像素（避免模糊）
    defaultZoomLevel: 0.99,       // 初始整体缩略
    smoothTileEdgesMinZoom: 1.1,
    crossOriginPolicy: "Anonymous",
    ajaxWithCredentials: true,    // 后端带鉴权时配合 SameSite cookie
  });
  viewer.addHandler("zoom", (e) => {
    zoomLabel.value = `${(e.zoom * 100).toFixed(0)}%`;
  });
}

function goHome()             { viewer?.viewport.goHome(); }
function zoomBy(factor: number){ viewer?.viewport.zoomBy(factor); }

// 切换切片时重建
watch(() => props.slideId, (id) => {
  viewer?.world.removeAll();
  viewer?.addTiledImage({ tileSources: `${apiBase}/medical/slide/${id}.dzi` });
});

onMounted(buildViewer);
onBeforeUnmount(() => { viewer?.destroy(); viewer = null; });
</script>

<style scoped>
.wsi-viewer { position: relative; width: 100%; height: 100%; background: #000; }
.osd-container { width: 100%; height: 100%; }
.wsi-toolbar { position: absolute; top: 8px; left: 8px;
  display: flex; gap: 8px; align-items: center; color: #fff; }
.zoom-label { font-size: 12px; opacity: 0.85; }
</style>
```

### 8.4 全屏弹窗 `WsiViewerDialog.vue`（新建，仿 `DicomViewerDialog.vue`）

要点：`destroy-on-close` + `@opened` 后才挂载 viewer（确保有尺寸），关闭触发 `viewer.destroy()` 防 WebGL/内存泄漏。

### 8.5 接入患者详情页

在 `views/module_medical/patient/detail.vue` 的「病理」Tab 里增加「查看切片」按钮，点击打开 `WsiViewerDialog`。slide_id 来源可暂用病理标本 id 或文件名约定，后续接入上传流水线后再改为数据库关联。

---

## 9. API 一览表

| 方法 | 路径 | 作用 | 返回类型 | 鉴权 |
|---|---|---|---|---|
| GET | `/medical/slide` | 列出所有切片 | `application/json` (SuccessResponse) | 是 |
| GET | `/medical/slide/{id}` | 单切片元信息 | `application/json` (SuccessResponse) | 是 |
| **GET** | **`/medical/slide/{id}.dzi`** | **Deep Zoom 描述文件** | **`text/xml`** | 是 |
| **GET** | **`/medical/slide/{id}_files/{L}/{C}_{R}.jpg`** | **单瓦片（核心放大接口）** | **`image/jpeg`** | 是 |
| GET | `/medical/slide/{id}/thumbnail` | 缩略图 | `image/jpeg` | 是 |
| GET | `/medical/slide/{id}/associated/{name}` | 关联图（label/macro） | `image/jpeg` | 是 |

> 全部叠加全局前缀 `/api/v1`。`.dzi` 与 `_files/...` 的 URL 模板刻意与 OpenSeadragon 默认吻合，前端只需一个 `tileSources` 字符串。

---

## 10. 分阶段演进路线

| 阶段 | 范围 | 验收标准 |
|---|---|---|
| **P0 闭环**（1~2 天） | 装 OpenSlide + 加配置 + slide 插件 + WsiViewer.vue，跑通动态切片 | 打开 `B1229048-2.svs`，平移/缩放流畅，瓦片逐级清晰 |
| **P1 体验**（半天） | 缩略图、标签图、缩放倍率显示、复位按钮、鉴权头接入 | 接入患者详情页「查看切片」按钮 |
| **P2 性能** | 离线切片流水线 + StaticFiles 托管 | 高并发零 CPU 占用，生产可用 |
| **P3 标准** | 加 IIIF Image API 端点（复用 OpenSlide 句柄，仅改协议层） | 可接入 OMERO / QuPath 等 |

### 离线切片命令（P2，需装 libvips）

```bash
vips dzsave "D:/wkdats/2026/07/301/WSI_sample/B1229048-2.svs" \
  "B1229048-2" --layout dz --tile-size 256 --overlap 0
# 产出：B1229048-2.dzi + B1229048-2_files/{L}/{C}_{R}.jpeg
```

FastAPI 端 P2 改动很小：把 `WSI_DZI_OUTPUT_DIR` 用 `StaticFiles` 挂到 `/medical/slide_dzi`，前端 `tileSources` 指向静态 `.dzi` 即可，协议层完全一致。

---

## 11. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Windows OpenSlide DLL 加载失败 | 后端无法启动 | 必须在 import 前 `os.add_dll_directory`；CI/Docker 用 Linux 镜像 `apt install python3-openslide` |
| 2.7 GB 文件内存 | 进程 OOM | OpenSlide 用 mmap 不全加载；进程级缓存 1 个句柄，不要每请求重开 |
| 瓦片洪水请求 | 后端 CPU 打满 | OpenSeadragon 自带 `imageLoaderLimit`；后端 `@lru_cache` + HTTP `Cache-Control: immutable` + ETag，浏览器/CDN 层缓存 |
| 首次缩略图慢 | 首屏等待 | 优先用 svs 内置 `associated_images['thumbnail']`，没有才降采样；可加后台预热任务 |
| CORS / 鉴权 | 瓦片加载失败 | 瓦片接口与现有 token 鉴权一致；`crossOriginPolicy:"Anonymous"` + `ajaxWithCredentials:true`，或 `beforeSend` 注入 Bearer（同 `DicomViewer.vue:248`） |
| 离线切片占磁盘 | 存储膨胀 | DZI 体积约为原图 1.1~1.3×；配置 retention 按访问热度淘汰 |
| 路径穿越攻击 | 任意文件读 | `repository.find_slide_path` 强校验 slide_id + `is_relative_to` 双保险 |

---

## 12. 与现有 DICOM 路线的关系

| 维度 | DICOM（已实现） | WSI（本方案） |
|---|---|---|
| 数据类型 | CT/MR 切片栈 | 病理整片大图 |
| 后端插件 | `module_medical/dicom` | `module_medical/slide` |
| 协议 | DICOMweb (QIDO/WADO-RS) | Deep Zoom (DZI) |
| 解码库 | pydicom | OpenSlide |
| 前端查看器 | cornerstone3D | OpenSeadragon |
| 数据入库 | 不入库（目录扫描） | 不入库（目录扫描） |
| 路由风格 | 协议接口裸返回 | 协议接口裸返回 |

两套平行存在、互不干扰，共享同一套配置/鉴权/路由发现机制。

---

## 13. 待审核决策点

请审核时重点确认以下几项（影响后续实现方向）：

1. **切片策略**：P0 是否同意动态切片起步？还是直接上离线切片（需额外引入 libvips 预处理流水线）？
2. **瓦片协议**：是否同意 DZI 起步、IIIF 留作 P3？若计划接入 OMERO/QuPath 等第三方系统，应提前到 P0。
3. **前端查看器**：是否同意引入 OpenSeadragon 作为新依赖？还是坚持复用 cornerstone3D（不推荐，需自实现瓦片调度）？
4. **OpenSlide 引入**：生产部署环境（Linux/Docker？）能否接受额外系统依赖 `openslide`？
5. **slide_id 来源**：切片与患者/标本的关联关系如何建模？是否需要建 `med_slide` 表持久化，还是先按文件名约定？

---

> **附：实现入口提示**
> 后端从 `backend/app/plugin/module_medical/slide/controller.py` 开始；前端从 `frontend/web/src/views/module_medical/patient/components/WsiViewer.vue` 开始。两个文件本文档均已给出可直接使用的骨架代码。
