"""医疗文件 — 服务层。"""

from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import asc, desc, func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_system.dict.model import DictDataModel
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.permission import Permission

from ..hospital.anon_model import AnonDicomSeriesModel, AnonExamModel, AnonPatientModel
from ..hospital.stats_query import _not_deleted_patient
from .crud import MedFilesCRUD
from .model import MedFilesModel
from .schema import MedicalFilesOutSchema


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

    @staticmethod
    def _resolve_order_columns(
        order_by: list[dict[str, str]] | None,
        extra: dict[str, Any] | None = None,
    ) -> list[Any]:
        """把 order_by（[{"field": "asc"}]）解析成 SQLAlchemy 排序表达式。

        extra 用于 select 里计算出来的列（如 file_size = coalesce(byte_size, 0)），
        这类列不是模型属性，无法通过 getattr 拿到。
        占位属性（file_name / file_type）与不存在的字段会被静默跳过，避免 asc(None) 报错；
        全部被过滤时回退到 id desc。
        """
        extra = extra or {}
        columns: list[Any] = []
        for order in order_by or []:
            if not isinstance(order, dict):
                continue
            for field, direction in order.items():
                # 注意：不能用 `extra.get(field) or ...`——SQLAlchemy 表达式未定义 __bool__，
                # 用 or 短路会抛 "Boolean value of this clause is not defined"。
                column = extra.get(field)
                if column is None:
                    column = getattr(MedFilesModel, field, None)
                # 只有真正的列表达式（带 __clause_element__）才能参与排序
                if column is None or not hasattr(column, "__clause_element__"):
                    continue
                columns.append(desc(column) if str(direction).lower() == "desc" else asc(column))
        return columns or [desc(MedFilesModel.id)]

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

        file_size 取自 lnrs_anon_dicom_series.byte_size：按
        dicom_series.dicom_study_uid == imaging_study.dicom_study_uid LEFT JOIN；
        dicom_series 未落库的 study 记为 0。
        """
        m = MedFilesModel
        s = AnonDicomSeriesModel

        conditions = []
        if exam_type:
            conditions.append(m.exam_type.in_(exam_type))

        # select 里计算出来的列，既用于返回也用于排序
        file_size_col = func.coalesce(s.byte_size, 0).label("file_size")

        sql = (
            select(m, file_size_col)
            .select_from(m)
            .outerjoin(s, s.dicom_study_uid == m.dicom_study_uid)
            .where(*conditions)
        )
        sql = await Permission(m, auth).filter_query(sql)
        sql = sql.order_by(
            *cls._resolve_order_columns(order_by, extra={"file_size": file_size_col})
        ).offset(offset).limit(limit)

        count_sql = select(func.count(m.id)).select_from(m).where(*conditions)
        count_sql = await Permission(m, auth).filter_query(count_sql)

        total = int((await auth.db.execute(count_sql)).scalar() or 0)
        rows = (await auth.db.execute(sql)).all()

        items: list[dict] = []
        for obj, file_size in rows:
            data = MedicalFilesOutSchema.model_validate(obj).model_dump()
            data["file_size"] = int(file_size or 0)
            items.append(data)

        return {
            "page_no": offset // limit + 1 if limit else 1,
            "page_size": limit or 10,
            "total": total,
            "items": items,
        }

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

        数据流（2026-09-15 重构自单 MedFilesModel 聚合；2026-09-20 issue-28 口径修订）：
        - record_count / patient_count / file_count：查 lnrs_anon_imaging_study（=MedFilesModel）
        - file_count = Σ imaging_study.sop_count（真实 DICOM 文件数，issue-28）。
          旧公式 record_count + Σ(series_count−1) 在 dicom_series 重构为 study 级
          （每 study 一行、series_count=1）后退化为 record_count，对省医
          （82,994 study / 2,901 万文件）严重失真；sop_count 经
          backfill_shengyi_sop_count.py 回填后与 series 层 Σ file_count 一致。
        - total_patient_count：患者主数据口径（issue-28 回切），与 medicalDashboard
          「患者总量」同源同值（StatsQuery.count_patients 的同一组条件，见下方代码注释）。
          不随 exam_type 过滤；与「患者数」（影像口径）、「有检查记录的患者数」
          （exam 口径）三个标签互斥、各自自描述，修复「总数 < 子集」倒挂。
        - total_size_bytes：查 lnrs_anon_dicom_series.byte_size 累加（ETL-2 重构后 study 级 byte_size 落库）
        - by_exam_type：GROUP BY AnonExamModel.exam_type（检查主表，值域=26 模态+Other），
          label 取 med_exam_type 字典翻译；分母 = 全部模态数量之和，反映检查数据的模态分布。
          2026-09-19 全局分布常显：本分组不随 exam_type 勾选过滤（center_type 仍生效）。
          issue-28：前端「模态类型」筛选器候选改由本分组驱动（裁剪到实际存在的
          exam_type），「全选」与「不选」等价（IN 覆盖全部值域 = 无过滤，有测试钉住）。
        - exam_patient_count：lnrs_anon_exam.patient_id 去重计数（一个患者多次检查会重复，
          必须 COUNT(DISTINCT)）；筛选条件与 exam_count 完全一致（exam_type→exam.exam_type，
          center_type→exam.center_code）。
        - 与 medicalDashboard 口径对照（2026-09-20 十表探针）：
            dashboard 「患者总量」 = total_patient_count（同源，两处数值恒等）
            medicalFiles 「患者数」 = patient_count（影像口径，shengyi 82,988）
            medicalFiles 「有检查记录的患者数」 = exam_patient_count（shengyi 66,635）
            exam∩imaging = 219 —— 三口径描述的是三个不同的人群截面，
            标签已各自自描述；「总患者数 ≥ 患者数」在全部筛选组合下恒成立。
        - 视图 v_imaging_study_counts 不直接用于本查询（它是 study×series 1:1 视图，
          不含 patient_count/file_count 维度）；改用 imaging_study + dicom_series 双源
        """
        m = MedFilesModel
        e = AnonExamModel
        s = AnonDicomSeriesModel
        # ---- record_count / patient_count / file_count：基于 MedFilesModel（=imaging_study）----
        # issue-28：file_count 改为 Σ imaging_study.sop_count（真实 DICOM 文件数）。
        # 旧公式 record_count + Σ(series_count−1) 在 series 表重构为 study 级后
        # 退化为 record_count（每个 study 一行 series、series_count=1），
        # 对省医（82,994 study / 2,901 万文件）严重失真。sop_count 经
        # backfill_shengyi_sop_count.py 回填后与 series 层 Σ file_count 一致。
        count_sql = select(
            func.count(m.id).label("record_count"),
            func.count(func.distinct(m.patient_id)).label("patient_count"),
            func.coalesce(func.sum(func.coalesce(m.sop_count, 0)), 0).label("file_count_sum"),
        )
        count_sql = cls._apply_search_conditions(
            count_sql, exam_type=exam_type, file_type=file_type, center_type=center_type
        )
        count_sql = await Permission(m, auth).filter_query(count_sql)
        count_row = (await auth.db.execute(count_sql)).one_or_none()
        record_count = int(count_row[0] or 0) if count_row else 0
        patient_count = int(count_row[1] or 0) if count_row else 0

        # ---- total_patient_count：患者主数据口径（issue-28 回切）----
        # 与 medicalDashboard「患者总量」同源同值（StatsQuery.count_patients，见
        # hospital/stats_query.py::_patient_filters）：lnrs_anon_patient 中
        # deleted_at IS NULL 且非占位（is_placeholder=FALSE，ADR 0012 数据型语义，
        # 2026-09-20 回填后占位行仅剩合成中心 5 行）+ center_code IN center_type。
        # 不随 exam_type 过滤 —— 人口是总体指标；与「患者数」（影像口径）、
        # 「有检查记录的患者数」（exam 口径）三标签互斥、各自自描述。
        total_patient_sql = (
            select(func.count())
            .select_from(AnonPatientModel)
            .where(
                _not_deleted_patient(),
                AnonPatientModel.is_placeholder.is_(False),
                *(
                    [AnonPatientModel.center_code.in_(center_type)]
                    if center_type
                    else []
                ),
            )
        )
        total_patient_count = int(
            (await auth.db.execute(total_patient_sql)).scalar() or 0
        )
        # ---- exam_patient_count：基于 AnonExamModel（=lnrs_anon_exam）的 patient_id 去重 ----
        # 一个患者会有多次检查，exam 表里 patient_id 会重复，必须 COUNT(DISTINCT patient_id)。
        # 筛选条件与 exam_count 完全一致（exam_type→exam.exam_type，center_type→exam.center_code）。
        # 与 medicalDashboard 的「患者总量」不同 —— 后者查 lnrs_anon_patient 全集。
        exam_patient_sql = select(func.count(func.distinct(e.patient_id)))
        exam_patient_sql = cls._apply_exam_conditions(
            exam_patient_sql, exam_type=exam_type, center_type=center_type
        )
        exam_patient_sql = await Permission(e, auth).filter_query(exam_patient_sql)
        exam_patient_count = int((await auth.db.execute(exam_patient_sql)).scalar() or 0)

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
        size_sql = select(
            func.coalesce(func.sum(s.byte_size), 0).label("total_size_bytes"),
        )
        size_sql = size_sql.join(
            m, s.dicom_study_uid == m.dicom_study_uid,
        )
        size_sql = cls._apply_search_conditions(
            size_sql, exam_type=exam_type, file_type=file_type, center_type=center_type
        )
        size_sql = await Permission(s, auth).filter_query(size_sql)
        size_row = (await auth.db.execute(size_sql)).one_or_none()
        total_size_bytes = int(size_row[0] or 0) if size_row else 0

        # file_count = Σ imaging_study.sop_count（见 count_sql 处注释，issue-28）
        file_count = int(count_row[2] or 0) if count_row else 0

        # ---- 字典 label ----
        exam_type_label_map = await cls._load_dict_labels(auth, "med_exam_type")

        # ---- by_exam_type：GROUP BY AnonExamModel.exam_type（检查主表，26 模态+Other）----
        # 2026-09-18 口径切换：imaging_study.modality 只有 CT，改 exam 表后
        # 分母 = 全部模态数量之和。
        # 2026-09-19 全局分布常显：本分组刻意不应用 exam_type 筛选（center_type 仍生效）。
        # 它是左侧「模态类型」筛选器的 facet 计数：若随勾选过滤，勾选组会变成
        # 100%、其余归 0，丢失全局分布信息（分母≠全部模态之和）。因此勾选态下
        # 各模态计数/百分比与初始加载一致；筛选统计由 KPI 区（exam_count 等）承担。
        # file_type 已废弃不参与本分组。
        by_exam_sql = select(e.exam_type, func.count().label("n")).group_by(e.exam_type)
        by_exam_sql = cls._apply_exam_conditions(
            by_exam_sql, exam_type=None, center_type=center_type
        )
        by_exam_sql = await Permission(e, auth).filter_query(by_exam_sql)
        by_exam_rows = (await auth.db.execute(by_exam_sql)).all()

        # 分母用本分组的合计数：分组只统计 study 记录条数，不含 series，
        # 与含 series 的 file_count 解耦，保证各项百分比之和 = 100%。
        exam_total = sum(int(cnt or 0) for _, cnt in by_exam_rows)

        by_exam_type: list[dict] = []
        for raw, cnt in by_exam_rows:
            if raw in (None, ""):
                continue
            value = str(raw)
            cnt = int(cnt)
            pct = round(cnt / exam_total * 100, 2) if exam_total else 0.0
            by_exam_type.append({
                "value": value,
                "label": exam_type_label_map.get(value, value),
                "count": cnt,
                "percentage": pct,
            })
        return {
            "file_count": file_count,
            "record_count": record_count,
            "total_patient_count": total_patient_count,
            "exam_patient_count": exam_patient_count,
            "patient_count": patient_count,
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
