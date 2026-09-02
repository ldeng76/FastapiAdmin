"""医疗文件 — 服务层。"""

from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.permission import Permission

from .crud import MedFilesCRUD
from .model import MedFilesModel
from .schema import MedicalFilesOutSchema


def _human_readable_size(num_bytes: int) -> str:
    """把字节数格式化成易读字符串（保留 2 位小数，自动进位到 KB/MB/GB/TB）。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} EB"


class MedFilesService:
    """医疗文件服务。"""

    # ------------------------------------------------------------------
    # 辅助：为 SQL 构造业务过滤条件（与 CRUDBase.__build_conditions 保持一致）
    # 不直接走 page() 是因为 distinct / 聚合用 SQL 原生更高效。
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_search_conditions(query, exam_type: list[str] | None, file_type: list[str] | None):
        """给 select 查询追加 exam_type/file_type 的 in 过滤 + 软删除 + 租户过滤。

        不追加 Permission 过滤（Permission.filter_query 作用于整个 select，在外部调用）。
        """
        m = MedFilesModel

        # 软删除
        if hasattr(m, "is_deleted"):
            query = query.where(getattr(m, "is_deleted") == False)

        # 多租户隔离
        # 模型 MedFilesModel 当前没有 tenant_id 字段，这里不做额外过滤，
        # 后续若新增 tenant_id 字段会自动匹配 CRUDBase 的策略。

        if exam_type:
            query = query.where(m.exam_type.in_(exam_type))
        if file_type:
            query = query.where(m.file_type.in_(file_type))

        return query

    @staticmethod
    async def _apply_permission(auth: AuthSchema, query):
        """对 select 追加 Permission 业务行级权限过滤，与 MedFilesCRUD 保持一致的可见性。"""
        p = Permission(model=MedFilesModel, auth=auth)
        return await p.filter_query(query)

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        offset: int,
        limit: int,
        order_by: list[dict[str, str]],
        exam_type: list[str] | None = None,
        file_type: list[str] | None = None,
    ) -> dict:
        """分页查询医疗文件列表。

        exam_type / file_type 为多选（IN）查询条件，为空则忽略。
        """
        search: dict[str, Any] = {}
        if exam_type:
            search["exam_type"] = ("in", exam_type)
        if file_type:
            search["file_type"] = ("in", file_type)

        return await MedFilesCRUD(auth).page(
            offset=offset,
            limit=limit,
            order_by=order_by,
            search=search,
            out_schema=MedicalFilesOutSchema,
        )

    # ------------------------------------------------------------------
    # 新增：字典接口 / 统计接口
    # ------------------------------------------------------------------

    @classmethod
    async def dict_file_types_service(
        cls,
        auth: AuthSchema,
        exam_type: list[str] | None = None,
    ) -> dict:
        """返回当前数据里实际出现过的 file_type 字典。

        参数:
            auth:       当前用户鉴权信息（控制行级可见性）
            exam_type:  可选，仅统计指定模态下出现过的文件类型
        """
        m = MedFilesModel
        sql = select(m.file_type).distinct().where(m.file_type.is_not(None), m.file_type != "")
        sql = cls._apply_search_conditions(sql, exam_type=exam_type, file_type=None)
        sql = await cls._apply_permission(auth, sql)
        sql = sql.order_by(m.file_type.asc())

        result = await auth.db.execute(sql)
        rows = [r for r, in result.all()]

        options = [{"label": str(x), "value": str(x)} for x in rows if x not in (None, "")]
        return {"file_type_options": options}

    @classmethod
    async def statistics_service(
        cls,
        auth: AuthSchema,
        exam_type: list[str] | None = None,
        file_type: list[str] | None = None,
    ) -> dict:
        """统计满足条件的数据：文件个数、患者数、总文件大小。

        参数:
            auth:       当前用户鉴权信息（控制行级可见性）
            exam_type:  可选，多选模态
            file_type:  可选，多选文件类型
        """
        m = MedFilesModel

        # 聚合
        sql = select(
            func.count(m.id).label("file_count"),
            func.count(func.distinct(m.patient_id)).label("patient_count"),
            func.coalesce(func.sum(m.file_size), 0).label("total_size_bytes"),
        )
        sql = cls._apply_search_conditions(sql, exam_type=exam_type, file_type=file_type)
        sql = await cls._apply_permission(auth, sql)

        result = await auth.db.execute(sql)
        row = result.one_or_none()
        file_count = 0
        patient_count = 0
        total_size_bytes = 0
        if row is not None:
            file_count = int(row[0] or 0)
            patient_count = int(row[1] or 0)
            total_size_bytes = int(row[2] or 0)

        return {
            "file_count": file_count,
            "patient_count": patient_count,
            "total_size_bytes": total_size_bytes,
            "total_size_text": _human_readable_size(total_size_bytes),
        }

    @classmethod
    def _resolve_file_path(cls, raw: str) -> Path:
        """解析数据库中的 file_path 字段为实际可访问的绝对路径。

        统一以 settings.FILES_DATA_ROOT 为根目录重定位：
        - 去掉开头的盘符（D:\\）、斜杠（/ 或 \\）等锚点
        - 拼接到 FILES_DATA_ROOT 下
        - 若已位于 FILES_DATA_ROOT 下则保持不变
        """
        root = Path(settings.FILES_DATA_ROOT)
        p = Path(raw)

        # 已在根目录下，直接返回
        try:
            p.relative_to(root)
            return p
        except ValueError:
            pass

        # 去掉锚点（盘符 D:\\ 或开头的 / \\），取纯相对部分
        rel = raw.lstrip("/\\")
        # 去掉 Windows 盘符（如 D:）
        if len(rel) >= 2 and rel[1] == ":":
            rel = rel[2:].lstrip("/\\")

        return root / rel

    @classmethod
    async def get_file_stream_service(
        cls, auth: AuthSchema, file_id: int
    ) -> tuple[Path, str]:
        """按文件ID查询记录并返回文件路径与文件名。

        返回:
            (file_path, file_name)

        异常:
            CustomException: 文件不存在或文件路径无效
        """
        obj: MedFilesModel | None = await MedFilesCRUD(auth).get(id=file_id)
        if not obj:
            raise CustomException(msg="文件不存在")

        if not obj.file_path:
            raise CustomException(msg="文件路径为空")

        path = cls._resolve_file_path(obj.file_path)
        if not path.is_file():
            raise CustomException(msg=f"文件不存在: {path}")

        return path, obj.file_name or path.name

    @classmethod
    async def get_study_instance_uid_service(
        cls, auth: AuthSchema, file_id: int
    ) -> str:
        """按文件ID读取 DICOM 文件，注册到 DICOM indexer 后返回 StudyInstanceUID。

        注册后即可通过 StudyInstanceUID 走 DICOMweb 接口预览。

        异常:
            CustomException: 文件不存在 / 非 DICOM 文件 / 无 StudyInstanceUID
        """
        path, _ = await cls.get_file_stream_service(auth=auth, file_id=file_id)

        # 注册到 DICOM indexer（内部用 stop_before_pixels 读头，不会加载像素）
        from app.plugin.module_medical.dicom.service import DicomService

        registered = DicomService.register_file(path)
        if not registered:
            raise CustomException(msg="文件解析失败或非可显示的 DICOM 图像")

        uid = registered.get("study_uid") or ""
        if not uid:
            raise CustomException(msg="该文件未包含 StudyInstanceUID")

        log.info(
            "DICOM 文件已注册到 indexer: file_id=%s, study_uid=%s, series_uid=%s, sop_uid=%s",
            file_id, uid, registered.get("series_uid"), registered.get("sop_uid"),
        )
        return uid
