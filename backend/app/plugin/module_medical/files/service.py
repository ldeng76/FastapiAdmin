"""医疗文件 — 服务层。"""

from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.permission import Permission

from ..hospital.anon_model import AnonExamModel
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
    def _apply_search_conditions(
        query,
        exam_type: list[str] | None,
        file_type: list[str] | None,
        center_type: list[str] | None = None,
    ):
        """给 select 查询追加 exam_type/file_type/center_type 的 in 过滤 + 软删除 + 租户过滤。

        不追加 Permission 过滤（Permission.filter_query 作用于整个 select，在外部调用）。
        center_type 筛选 MedFilesModel.file_type（即 center_code）。
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
        if center_type:
            query = query.where(m.file_type.in_(center_type))

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
        center_type: list[str] | None = None,
    ) -> dict:
        """统计满足条件的数据：文件个数、患者数、总文件大小、各模态/文件类型分组。

        参数:
            auth:        当前用户鉴权信息（控制行级可见性）
            exam_type:   可选，多选模态
            file_type:   可选，多选文件类型
            center_type: 可选，多选中心筛选
        """
        m = MedFilesModel

        # 聚合
        sql = select(
            func.count(m.id).label("file_count"),
            func.count(func.distinct(m.patient_id)).label("patient_count"),
            # func.coalesce(func.sum(m.file_size), 0).label("total_size_bytes"),
        )
        sql = cls._apply_search_conditions(sql, exam_type=exam_type, file_type=file_type, center_type=center_type)
        sql = await cls._apply_permission(auth, sql)

        result = await auth.db.execute(sql)
        row = result.one_or_none()
        file_count = 0
        patient_count = 0
        total_size_bytes = 0
        if row is not None:
            file_count = int(row[0] or 0)
            patient_count = int(row[1] or 0)
            # total_size_bytes = int(row[1] or 0)

        # 检查量：直接查 AnonExamModel 行数（按 exam_type + center_type 筛选）
        exam_count_sql = select(func.count(AnonExamModel.anon_exam_id))
        if exam_type:
            exam_count_sql = exam_count_sql.where(AnonExamModel.exam_type.in_(exam_type))
        if center_type:
            exam_count_sql = exam_count_sql.where(AnonExamModel.center_code.in_(center_type))
        exam_count_result = await auth.db.execute(exam_count_sql)
        exam_count = int(exam_count_result.scalar() or 0)

        # 各模态分组统计（直接用数据里的 exam_type 原始值，不查字典）
        by_exam_type: list[dict] = []
        exam_sql = select(
            m.exam_type,
            func.count(m.id),
        ).where(m.exam_type.is_not(None), m.exam_type != "")
        exam_sql = cls._apply_search_conditions(exam_sql, exam_type=exam_type, file_type=file_type, center_type=center_type)
        exam_sql = await cls._apply_permission(auth, exam_sql)
        exam_sql = exam_sql.group_by(m.exam_type)
        exam_result = await auth.db.execute(exam_sql)
        exam_rows = exam_result.all()

        for value, count in exam_rows:
            cnt = int(count or 0)
            pct = round(cnt / file_count * 100, 2) if file_count > 0 else 0.0
            by_exam_type.append({
                "value": str(value),
                "label": str(value),
                "count": cnt,
                "percentage": pct,
            })

        # 各文件类型分组统计
        by_file_type: list[dict] = []
        ft_sql = select(
            m.file_type,
            func.count(m.id),
        ).where(m.file_type.is_not(None), m.file_type != "")
        ft_sql = cls._apply_search_conditions(ft_sql, exam_type=exam_type, file_type=file_type, center_type=center_type)
        ft_sql = await cls._apply_permission(auth, ft_sql)
        ft_sql = ft_sql.group_by(m.file_type)
        ft_result = await auth.db.execute(ft_sql)
        ft_rows = ft_result.all()

        for value, count in ft_rows:
            cnt = int(count or 0)
            pct = round(cnt / file_count * 100, 2) if file_count > 0 else 0.0
            by_file_type.append({
                "value": str(value),
                "label": str(value),
                "count": cnt,
                "percentage": pct,
            })

        return {
            "file_count": file_count,
            "patient_count": patient_count,
            "exam_count": exam_count,
            "total_size_bytes": total_size_bytes,
            "total_size_text": _human_readable_size(total_size_bytes),
            "by_exam_type": by_exam_type,
            "by_file_type": by_file_type,
        }

    @classmethod
    def _resolve_file_path(cls, raw: str) -> Path:

        root = Path(settings.DICOM_DATA_DIR)
        p = Path(raw)

        # raw 的前缀部分与 DICOM_DATA_DIR 重合（如 raw=D:\data\dicom\x.dcm，
        # root=D:\data\dicom），说明已是绝对路径且在数据目录下，直接返回
        try:
            raw_resolved = str(p.resolve())
            root_resolved = str(root.resolve())
            if raw_resolved.startswith(root_resolved):
                return p
        except Exception:
            pass

        # 也处理未 resolve 的字符串前缀匹配（路径不存在时 resolve 会失败）
        raw_st = raw.replace("\\", "/").rstrip("/")
        root_st = str(root).replace("\\", "/").rstrip("/")
        if raw_st.startswith(root_st):
            return p

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
            CustomException: 记录不存在 / file_path 为空
            CustomException: 路径指向目录（不能流式下载整个目录，请用 DICOMweb 预览）
            CustomException: 磁盘上文件不存在
        """
        obj: MedFilesModel | None = await MedFilesCRUD(auth).get(id=file_id)
        if not obj:
            raise CustomException(msg="文件不存在")

        if not obj.file_path:
            raise CustomException(msg="文件路径为空")

        path = cls._resolve_file_path(obj.file_path)
        if path.is_dir():
            raise CustomException(
                msg="该路径为目录（整份 DICOM study），不能下载单个文件；请通过 DICOMweb 接口预览",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not path.is_file():
            raise CustomException(msg=f"文件不存在: {path}")

        return path, obj.file_name or path.name

    @classmethod
    async def check_file_existence_service(
        cls,
        auth: AuthSchema,
        *,
        file_id: int | None = None,
        anon_exam_id: str | None = None,
    ) -> dict:
        """校验文件或目录在磁盘上是否存在。

        file_id / anon_exam_id 二选一。
        DB 的 image_path 指向单文件或 Study 目录都算存在（file_id 返回命中的 study_key）。
        """
        search: dict[str, Any] = {}
        if file_id is not None:
            search["id"] = file_id
        elif anon_exam_id:
            search["anon_exam_id"] = anon_exam_id
        else:
            return {"file_id": None, "exists": False}

        objs = await MedFilesCRUD(auth).list(search=search)
        obj: MedFilesModel | None = objs[0] if objs else None
        if obj is None or not obj.file_path:
            return {"file_id": obj.id if obj else None, "exists": False}

        path = cls._resolve_file_path(obj.file_path)
        exists = path.is_file() or path.is_dir()
        return {"file_id": obj.id, "exists": bool(exists)}

    @classmethod
    async def get_study_instance_uid_service(
        cls, auth: AuthSchema, file_id: int
    ) -> str:
        """按文件ID读取 DICOM 文件/目录，注册到 DICOM indexer 后返回 StudyInstanceUID。

        真实数据两种分支：
            A) DB file_path 是单个 DICOM 文件 → register_file 后再 register_folder 补全
            B) DB file_path 是一个 Study 目录（里面多文件） → 直接 register_folder

        注册后即可通过 StudyInstanceUID 走 DICOMweb 接口预览。

        异常:
            CustomException: 记录不存在 / 路径无效 / 目录里没有合法 DICOM 图像 / 无 StudyInstanceUID
        """
        from app.plugin.module_medical.dicom.service import DicomService

        # 不要走 get_file_stream_service（它会拒绝目录），自己解 path
        obj: MedFilesModel | None = await MedFilesCRUD(auth).get(id=file_id)
        if not obj:
            raise CustomException(msg="文件不存在")
        if not obj.file_path:
            raise CustomException(msg="文件路径为空")

        path = cls._resolve_file_path(obj.file_path)

        # 分支 B：path 本身是 Study 文件夹（典型医院目录组织方式）
        if path.is_dir():
            folder_reg = DicomService.register_folder(path)
            if not folder_reg or not folder_reg.get("study_uid"):
                raise CustomException(msg="目录中未解析到合法的 DICOM 图像")
            uid = folder_reg["study_uid"]
            log.info(
                "DICOM 按目录已注册到 indexer: file_id=%s folder=%s study=%s series=%d instances=%d",
                file_id,
                path,
                uid,
                folder_reg.get("series_count", 0),
                folder_reg.get("instance_count", 0),
            )
            return uid

        # 分支 A：单个文件 → 先注册文件，再把父目录补齐
        if not path.is_file():
            raise CustomException(msg=f"文件不存在: {path}")

        registered = DicomService.register_file(path)
        if not registered:
            raise CustomException(msg="文件解析失败或非可显示的 DICOM 图像")

        uid = registered.get("study_uid") or ""
        if not uid:
            raise CustomException(msg="该文件未包含 StudyInstanceUID")

        folder_reg = DicomService.register_folder(path.parent)
        if folder_reg and folder_reg.get("study_uid"):
            uid = folder_reg["study_uid"]
            log.info(
                "DICOM study 文件夹已批量注册: file_id=%s folder=%s study=%s series=%d instances=%d",
                file_id,
                path.parent,
                uid,
                folder_reg.get("series_count", 0),
                folder_reg.get("instance_count", 0),
            )
        else:
            log.info(
                "DICOM 文件已注册到 indexer: file_id=%s, study_uid=%s, series_uid=%s, sop_uid=%s",
                file_id, uid, registered.get("series_uid"), registered.get("sop_uid"),
            )
        return uid
