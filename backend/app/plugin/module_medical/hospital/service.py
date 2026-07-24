"""医院管理模块 service。

注册流程联动租户体系：
1. 校验医院 code/name 唯一性
2. 调用 TenantService.create_service 创建对应租户（自动建 {code}_admin 初始管理员 + 配额，
   日志已打印临时密码）
3. 创建 HospitalModel（lifecycle_status=registered），关联 tenant_id
"""

from __future__ import annotations

from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_system.tenant.schema import TenantCreateSchema
from app.api.v1.module_system.tenant.service import TenantService
from app.core.exceptions import CustomException
from app.core.logger import log

from sqlalchemy import func, select

from .crud import HospitalCRUD
from .anon_query import anon_data_summary
from .model import (
    HospitalModel,
    HospitalStatus,
)
from .schema import HospitalCreate, HospitalOut, HospitalUpdate

# 生命周期状态机流转规则
# key: 当前状态 → value: 允许流转到的状态列表
LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    HospitalStatus.REGISTERED.value: [HospitalStatus.MAPPING_CONFIGURED.value],
    HospitalStatus.MAPPING_CONFIGURED.value: [
        HospitalStatus.DATA_IMPORTED.value,
        HospitalStatus.MAPPING_CONFIGURED.value,  # 允许重新编辑映射
    ],
    HospitalStatus.DATA_IMPORTED.value: [
        HospitalStatus.LIVE.value,
        HospitalStatus.DATA_IMPORTED.value,  # 允许重新导入
    ],
    HospitalStatus.LIVE.value: [HospitalStatus.DATA_IMPORTED.value],  # 下线
}

# 各状态是否允许直接编辑映射
MAPPING_EDITABLE_STATUSES = {
    HospitalStatus.REGISTERED.value,
    HospitalStatus.MAPPING_CONFIGURED.value,
    HospitalStatus.DATA_IMPORTED.value,
}

# 各状态是否允许触发导入
IMPORTABLE_STATUSES = {
    HospitalStatus.MAPPING_CONFIGURED.value,
    HospitalStatus.DATA_IMPORTED.value,
}


class HospitalService:
    """医院管理服务"""

    @classmethod
    async def create_service(cls, auth: AuthSchema, data: HospitalCreate) -> dict:
        """注册医院：建租户 + 初始管理员 + 配额 → 建医院记录。

        参数:
            auth: 认证上下文（含 db 会话）
            data: 医院注册入参

        返回:
            dict: HospitalOut 序列化结果

        异常:
            CustomException: code/name 重复、租户创建失败时抛出
        """
        # 1. 唯一性校验
        if await HospitalCRUD(auth).get(code=data.code):
            raise CustomException(msg="创建失败，医院编码已存在")
        if await HospitalCRUD(auth).get(name=data.name):
            raise CustomException(msg="创建失败，医院名称已存在")

        # 2. 创建对应租户（含 {code}_admin 初始管理员 + 配额，临时密码已打印到日志）
        tenant_data = TenantCreateSchema(
            name=data.name,
            code=data.code,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            address=data.address,
        )
        try:
            tenant_result = await TenantService.create_service(auth=auth, data=tenant_data)
        except CustomException:
            raise
        except Exception as e:
            log.error(f"为医院[{data.name}]创建租户失败: {e!s}")
            raise CustomException(msg=f"创建关联租户失败: {e!s}")

        tenant_id = tenant_result.get("id")
        if not tenant_id:
            raise CustomException(msg="创建关联租户失败：未返回租户ID")

        # 3. 创建医院记录（lifecycle_status=registered）
        hospital_obj = HospitalModel(
            code=data.code,
            name=data.name,
            full_name=data.full_name,
            tenant_id=tenant_id,
            lifecycle_status=HospitalStatus.REGISTERED.value,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            address=data.address,
            data_dir=data.data_dir,
        )
        try:
            # 直接用 auth.db 写入（绕过 CRUDBase.create 的 tenant_id 自动填充，
            # 因 HospitalModel 不继承 TenantMixin，需显式构造）
            auth.db.add(hospital_obj)
            # 手动填充 UserMixin 审计字段
            if auth.user:
                hospital_obj.created_id = auth.user.id
                hospital_obj.updated_id = auth.user.id
            await auth.db.flush()
            await auth.db.refresh(hospital_obj)
        except Exception as e:
            log.error(f"创建医院记录失败（租户已创建 tenant_id={tenant_id}）: {e!s}")
            raise CustomException(msg=f"创建医院记录失败: {e!s}")

        # 4. 注册联动：若指定 template_code，复制模板规则到 med_mapping_rule
        #    并推进 lifecycle_status 到 mapping_configured
        if data.template_code:
            try:
                from .mapping_service import MappingRuleService
                from .template_data import get_template

                template = get_template(data.template_code)
                if template:
                    await MappingRuleService.apply_template_service(
                        auth=auth,
                        hospital_id=hospital_obj.id,
                        template_code=data.template_code,
                    )
                    hospital_obj.lifecycle_status = HospitalStatus.MAPPING_CONFIGURED.value
                    await auth.db.flush()
                    log.info(
                        f"应用模板[{data.template_code}]到医院[{hospital_obj.id}]成功"
                    )
                else:
                    log.warning(
                        f"注册时指定的 template_code[{data.template_code}]不存在，跳过模板应用"
                    )
            except Exception as e:
                # 模板应用失败不阻断注册（医院已创建，状态保持 registered）
                log.error(f"应用模板失败（医院已创建）: {e!s}")

        log.info(
            f"注册医院成功: code={hospital_obj.code}, name={hospital_obj.name}, "
            f"tenant_id={tenant_id}, hospital_id={hospital_obj.id}, "
            f"lifecycle_status={hospital_obj.lifecycle_status}"
        )

        result = HospitalOut.model_validate(hospital_obj).model_dump()
        return result

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int,
        page_size: int,
        order_by: list[dict[str, str]] | None = None,
        search: dict | None = None,
    ) -> dict[str, Any]:
        """医院分页列表。"""
        return await HospitalCRUD(auth).page_crud(
            offset=(page_no - 1) * page_size,
            limit=page_size,
            order_by=order_by,
            search=search or {},
            preload=["tenant"],
        )

    @classmethod
    async def detail_service(cls, auth: AuthSchema, id: int) -> dict:
        """医院详情。"""
        obj = await HospitalCRUD(auth).get_by_id_crud(id=id, preload=["tenant"])
        if not obj:
            raise CustomException(msg="医院不存在")
        return HospitalOut.model_validate(obj).model_dump()

    @classmethod
    async def update_service(cls, auth: AuthSchema, id: int, data: HospitalUpdate) -> dict:
        """更新医院信息（不允许改 code/tenant_id/lifecycle_status）。"""
        obj = await HospitalCRUD(auth).get_by_id_crud(id=id)
        if not obj:
            raise CustomException(msg="医院不存在")

        # name 唯一性校验（排除自身）
        if data.name is not None:
            exist = await HospitalCRUD(auth).get(name=data.name)
            if exist and exist.id != id:
                raise CustomException(msg="更新失败，医院名称重复")

        updated = await HospitalCRUD(auth).update_crud(id=id, data=data)
        if not updated:
            raise CustomException(msg="更新失败")
        return HospitalOut.model_validate(updated).model_dump()

    @classmethod
    async def get_anon_data_summary_service(
        cls,
        auth: AuthSchema,
        id: int,
        center_codes: list[str] | None = None,
    ) -> dict:
        """获取医院 anon 数据摘要（lnrs_anon_* 各表行数），供上线前校验和前端展示。

        与 get_data_summary_service 的区别：
        - 数据源：lnrs_anon_* 表（parquet 直入），不是 med_*（ETL-1 中间层）。
        - 过滤维度：center_code（anon 表无 tenant_id），不是 tenant_id。
        - 字段：tables key 是 anon 表名（patient/exam/report_text/exam_detail/visit/surgery/ingest_batch）。

        Args:
            auth: 认证上下文。
            id: 医院 ID。
            center_codes: 限定到这些中心；None 表示统计该医院的所有 anon 数据。
                注意：当前实现未实现 hospital↔center 映射，调用方需自己传 center_codes。
                若 hospital.code 字段已是 center_code（如 "zhujiang"），可由调用方传 [hospital.code]。
        """
        hospital = await HospitalCRUD(auth).get_by_id_crud(id=id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        counts = await anon_data_summary(auth.db, center_codes=center_codes)

        return {
            "hospital_id": hospital.id,
            "lifecycle_status": hospital.lifecycle_status,
            "center_codes": center_codes or [],
            "total_rows": counts["total_rows"],
            "tables": {k: v for k, v in counts.items() if k != "total_rows"},
        }

    @classmethod
    async def go_online_service(cls, auth: AuthSchema, id: int) -> dict:
        """上线发布：data_imported → live。

        校验：
        - 当前状态为 data_imported
        - 至少一张 anon 表有数据（total_rows > 0）

        2026-07-24 改：改调 anon 体系（get_anon_data_summary_service）替代 med_* 体系。
        center_codes 用 hospital.code（若是 shengyi/xinqiao/zhujiang 之一；否则空列表，
        表示统计所有 anon 数据）。
        """
        hospital = await HospitalCRUD(auth).get_by_id_crud(id=id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        current = hospital.lifecycle_status
        if current != HospitalStatus.DATA_IMPORTED.value:
            raise CustomException(
                msg=f"当前状态[{current}]不允许上线，需先完成数据导入",
                code=400,
                status_code=400,
            )

        # 校验数据（anon 体系）
        # 当前简化：把 hospital.code 作为 center_code（仅当它是 shengyi/xinqiao/zhujiang 之一）
        # 未来实现 hospital↔center 映射后，这里改成 [hospital.center_code]
        from .anon_etl_service import KNOWN_CENTERS
        center_codes = [hospital.code] if hospital.code in KNOWN_CENTERS else None
        summary = await cls.get_anon_data_summary_service(
            auth=auth, id=id, center_codes=center_codes
        )
        if summary["total_rows"] <= 0:
            raise CustomException(
                msg="无法上线：医院无任何 anon 数据（lnrs_anon_* 表为空）",
                code=400,
                status_code=400,
            )

        # 推进状态
        hospital.lifecycle_status = HospitalStatus.LIVE.value
        await auth.db.flush()
        await auth.db.refresh(hospital)

        log.info(
            f"医院上线: id={hospital.id}, code={hospital.code}, "
            f"total_rows={summary['total_rows']}"
        )

        result = HospitalOut.model_validate(hospital).model_dump()
        return result

    @classmethod
    async def go_offline_service(cls, auth: AuthSchema, id: int) -> dict:
        """下线：live → data_imported。"""
        hospital = await HospitalCRUD(auth).get_by_id_crud(id=id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)

        current = hospital.lifecycle_status
        if current != HospitalStatus.LIVE.value:
            raise CustomException(
                msg=f"当前状态[{current}]不允许下线，仅 LIVE 状态可下线",
                code=400,
                status_code=400,
            )

        hospital.lifecycle_status = HospitalStatus.DATA_IMPORTED.value
        await auth.db.flush()
        await auth.db.refresh(hospital)

        log.info(f"医院下线: id={hospital.id}, code={hospital.code}")

        result = HospitalOut.model_validate(hospital).model_dump()
        return result

    @classmethod
    async def can_edit_mapping(cls, hospital: HospitalModel) -> bool:
        """检查当前状态是否允许编辑映射（LIVE 需先下线）。"""
        return hospital.lifecycle_status in MAPPING_EDITABLE_STATUSES

    @classmethod
    async def assert_can_edit_mapping(cls, hospital: HospitalModel) -> None:
        """不允许编辑映射时抛出 409。"""
        if hospital.lifecycle_status == HospitalStatus.LIVE.value:
            raise CustomException(
                msg="请先下线医院（LIVE → DATA_IMPORTED）后再修改映射",
                code=409,
                status_code=409,
            )
        if hospital.lifecycle_status not in MAPPING_EDITABLE_STATUSES:
            raise CustomException(
                msg=f"当前状态[{hospital.lifecycle_status}]不允许编辑映射",
                code=409,
                status_code=409,
            )
