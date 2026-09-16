"""医疗文件 — 服务层。"""

from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_system.dict.model import DictDataModel
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log

from app.core.permission import Permission

from ..hospital.anon_model import AnonDicomSeriesModel, AnonExamModel, AnonPatientModel
from .model import MedFilesModel
from .schema import MedicalFilesOutSchema
from .crud import MedFilesCRUD

def _human_readable_size(num_bytes: int | None) -> str | None:
    """把字节数格式化成易读字符串（保留 2 位小数，自动进位到 KB/MB/GB/TB）。"""
    if num_bytes is None:
        return None
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
        """给 select 查询追加 exam_type/center_type 的 in 过滤 + 软删除 + 租户过滤。

        不追加 Permission 过滤（Permission.filter_query 作用于整个 select，在外部调用）。
        file_type 数据库无对应列，已废弃；center_type 筛选 MedFilesModel.center_code。
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
        if center_type:
            query = query.where(m.center_code.in_(center_type))

        return query
    @staticmethod
    def _apply_exam_conditions(
        query,
        exam_type: list[str] | None,
        center_type: list[str] | None,
    ):
        """给 select 查询追加 exam 表的 in 过滤（不追加 Permission 过滤）。

        用于 exam_count / by_exam_type_business 等基于 AnonExamModel 的查询，
        与 _apply_search_conditions 平行存在（后者绑定 MedFilesModel）。
        """
        e = AnonExamModel
        if exam_type:
            query = query.where(e.exam_type.in_(exam_type))
        if center_type:
            query = query.where(e.center_code.in_(center_type))
        return query


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

        exam_type 为多选（IN）查询条件，为空则忽略。
        file_type 数据库无对应列，已废弃，不参与筛选。
        """
        search: dict[str, Any] = {}
        if exam_type:
            search["exam_type"] = ("in", exam_type)

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
        """返回文件类型字典。

        file_type 数据库无对应列，固定返回 dcm。
        """
        return {"file_type_options": [{"label": "dcm", "value": "dcm"}]}

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
            exam_type:   可选，多选模态（MedFilesModel.exam_type 物理映射 imaging_study.modality）
            file_type:   可选，多选文件类型（MedFilesModel.file_type 物理映射 imaging_study.center_code）
            center_type: 可选，多选中心筛选（按 MedFilesModel.file_type 过滤）

        数据流（2026-09-15 重构自单 MedFilesModel 聚合）：
        - file_count / patient_count / exam_count：查 lnrs_anon_imaging_study（=MedFilesModel）
        - total_size_bytes：查 lnrs_anon_dicom_series.byte_size 累加（ETL-2 重构后 study 级 byte_size 落库）
        - by_exam_type：GROUP BY MedFilesModel.exam_type（即 imaging_study.modality），label 取 med_exam_type 字典
          翻译；当前 h196_3 上 modality 100%='CT'，只会返回 1 行（事实告知用户）
        - by_file_type：GROUP BY MedFilesModel.file_type（即 imaging_study.center_code），label 取 med_center 字典翻译
        - 视图 v_imaging_study_counts 不直接用于本查询（它是 study×series 1:1 视图，
          不含 patient_count/file_count 维度）；改用 imaging_study + dicom_series 双源
        """
        m = MedFilesModel
        e = AnonExamModel

        # ---- file_count / record_count / patient_count：基于 MedFilesModel（=imaging_study）----
        count_sql = select(
            func.count(m.id).label("file_count"),
            func.count(m.id).label("record_count"),
            func.count(func.distinct(m.patient_id)).label("patient_count"),
        )
        count_sql = cls._apply_search_conditions(
            count_sql, exam_type=exam_type, file_type=file_type, center_type=center_type
        )
        count_sql = await Permission(m, auth).filter_query(count_sql)
        count_row = (await auth.db.execute(count_sql)).one_or_none()
        file_count = int(count_row[0] or 0) if count_row else 0
        record_count = int(count_row[1] or 0) if count_row else 0
        patient_count = int(count_row[2] or 0) if count_row else 0

        # ---- total_patient_count：基于 AnonPatientModel（=lnrs_anon_patient 未删除行数）----
        total_patient_sql = select(func.count(AnonPatientModel.patient_id)).where(
            AnonPatientModel.deleted_at.is_(None)
        )
        if center_type:
            total_patient_sql = total_patient_sql.where(
                AnonPatientModel.center_code.in_(center_type)
            )
        if exam_type:
            # exam_type 是多选列表，必须用 in_（== list 会让 SQLAlchemy/asyncpg 无法编码参数）；
            # 子查询需显式 scalar_subquery()，再交给 in_ 使用。
            exam_patient_subq = cls._apply_exam_conditions(
                select(e.patient_id), exam_type=exam_type, center_type=None
            )
            exam_patient_subq = await Permission(e, auth).filter_query(exam_patient_subq)
            total_patient_sql = total_patient_sql.where(
                AnonPatientModel.patient_id.in_(exam_patient_subq.distinct().scalar_subquery())
            )
        total_patient_sql = await Permission(AnonPatientModel, auth).filter_query(total_patient_sql)
        total_patient_count = int((await auth.db.execute(total_patient_sql)).scalar() or 0)

        # ---- exam_count：基于 AnonExamModel（=lnrs_anon_exam 行数）----
        # 注意：exam_count 不等于 file_count —— 一次临床检查可能 0/N 个影像文件。
        # 筛选条件映射：exam_type→exam.exam_type，center_type→exam.center_code。
        exam_sql = select(func.count(e.anon_exam_id))
        exam_sql = cls._apply_exam_conditions(exam_sql, exam_type=exam_type, center_type=center_type)
        exam_sql = await Permission(e, auth).filter_query(exam_sql)
        exam_count = int((await auth.db.execute(exam_sql)).scalar() or 0)

        # ---- total_size_bytes：从 dicom_series 累加（Permission 绑 dicom_series）----
        # center_type 按 imaging_study.center_code 过滤；exam_type/file_type 在 byte_size 维度下
        # 走同一筛选，保持 KPI 与 by_exam_type/by_center 一致。
        size_sql = select(func.coalesce(func.sum(AnonDicomSeriesModel.byte_size), 0))
        size_sql = size_sql.join(
            m, AnonDicomSeriesModel.dicom_study_uid == m.file_name,
        )
        size_sql = cls._apply_search_conditions(
            size_sql, exam_type=exam_type, file_type=file_type, center_type=center_type
        )
        size_sql = await Permission(AnonDicomSeriesModel, auth).filter_query(size_sql)
        total_size_bytes = int((await auth.db.execute(size_sql)).scalar() or 0)

        # ---- 字典 label ----
        exam_type_label_map = await cls._load_dict_labels(auth, "med_exam_type")

        # ---- by_exam_type：GROUP BY MedFilesModel.exam_type（=imaging_study.modality）----
        by_exam_sql = select(m.exam_type, func.count().label("n")).group_by(m.exam_type)
        by_exam_sql = cls._apply_search_conditions(
            by_exam_sql, exam_type=exam_type, file_type=file_type, center_type=center_type
        )
        by_exam_sql = await Permission(m, auth).filter_query(by_exam_sql)
        by_exam_rows = (await auth.db.execute(by_exam_sql)).all()

        by_exam_type: list[dict] = []
        for raw, cnt in by_exam_rows:
            if raw in (None, ""):
                continue
            value = str(raw)
            cnt = int(cnt)
            pct = round(cnt / file_count * 100, 2) if file_count else 0.0
            by_exam_type.append({
                "value": value,
                "label": exam_type_label_map.get(value, value),
                "count": cnt,
                "percentage": pct,
            })
        by_exam_type.sort(key=lambda x: -x["count"])

        return {
            "file_count": file_count,
            "record_count": record_count,
            "patient_count": patient_count,
            "total_patient_count": total_patient_count,
            "exam_count": exam_count,
            "total_size_bytes": total_size_bytes,
            "total_size_text": _human_readable_size(total_size_bytes),
            "by_exam_type": by_exam_type,
        }

    @staticmethod
    async def _load_dict_labels(auth: AuthSchema, dict_type: str) -> dict[str, str]:
        """从 sys_dict_data 加载 {dict_value: dict_label} 映射（复用系统字典）。

        复用 stats_query._load_dict_labels 的同款 SQL，避免 files service 单独维护翻译表。
        """
        sql = select(DictDataModel.dict_value, DictDataModel.dict_label).where(
            DictDataModel.dict_type == dict_type
        )
        result = await auth.db.execute(sql)
        return {value: label for value, label in result.all()}

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
