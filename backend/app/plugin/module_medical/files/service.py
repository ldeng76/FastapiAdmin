"""医疗文件 — 服务层。"""

from pathlib import Path
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log

from .crud import MedFilesCRUD
from .model import MedFilesModel
from .schema import MedicalFilesOutSchema


class MedFilesService:
    """医疗文件服务。"""

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
