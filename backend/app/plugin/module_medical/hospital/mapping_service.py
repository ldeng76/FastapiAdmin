"""映射规则服务。

批量替换语义：调用 replace_service 时，先删除该院所有旧规则，再批量插入新规则。
这是"全量替换"，而非增量更新——前端提交完整的规则集。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.logger import log

from .crud import HospitalCRUD
from .model import MappingRuleModel
from .schema import MappingRuleBatch, MappingRuleOut
from .template_data import get_template, list_templates


class MappingRuleService:
    """映射规则管理服务"""

    @classmethod
    async def list_service(cls, auth: AuthSchema, hospital_id: int) -> list[dict]:
        """列出某医院的全部映射规则。"""
        await cls._ensure_hospital_exists(auth, hospital_id)
        stmt = (
            select(MappingRuleModel)
            .where(
                MappingRuleModel.hospital_id == hospital_id,
                MappingRuleModel.is_deleted == False,  # noqa: E712
            )
            .order_by(MappingRuleModel.tgt_table, MappingRuleModel.sort, MappingRuleModel.id)
        )
        result = await auth.db.execute(stmt)
        rules = result.scalars().all()
        return [MappingRuleOut.model_validate(r).model_dump() for r in rules]

    @classmethod
    async def replace_service(
        cls, auth: AuthSchema, hospital_id: int, data: MappingRuleBatch
    ) -> list[dict]:
        """全量替换某医院的映射规则。

        1. 校验医院存在
        2. 校验规则集内 (src_table, src_field) 不重复
        3. 删除该院所有旧规则（物理删除，非软删除——映射规则无需保留历史）
        4. 批量插入新规则
        """
        hospital = await cls._ensure_hospital_exists(auth, hospital_id)

        # 校验状态允许编辑映射（LIVE 需先下线）
        from .service import HospitalService
        await HospitalService.assert_can_edit_mapping(hospital)

        # 校验规则集内 (src_table, src_field) 唯一性
        seen: set[tuple[str, str]] = set()
        for rule in data.rules:
            key = (rule.src_table, rule.src_field)
            if key in seen:
                raise CustomException(
                    msg=f"规则集内存在重复映射: src_table={rule.src_table}, src_field={rule.src_field}",
                    code=400,
                    status_code=400,
                )
            seen.add(key)

        # 删除旧规则
        await auth.db.execute(
            delete(MappingRuleModel).where(MappingRuleModel.hospital_id == hospital_id)
        )

        # 批量插入新规则
        new_rules = []
        for rule_in in data.rules:
            obj = MappingRuleModel(
                hospital_id=hospital_id,
                src_table=rule_in.src_table,
                src_field=rule_in.src_field,
                tgt_table=rule_in.tgt_table,
                tgt_field=rule_in.tgt_field,
                transform_type=rule_in.transform_type,
                transform_value=rule_in.transform_value,
                description=rule_in.description,
                sort=rule_in.sort,
            )
            if auth.user:
                obj.created_id = auth.user.id
                obj.updated_id = auth.user.id
            auth.db.add(obj)
            new_rules.append(obj)

        await auth.db.flush()
        # 刷新以拿到 id
        for obj in new_rules:
            await auth.db.refresh(obj)

        log.info(f"医院[{hospital_id}]映射规则已全量替换，共 {len(new_rules)} 条")
        return [MappingRuleOut.model_validate(r).model_dump() for r in new_rules]

    @classmethod
    async def apply_template_service(
        cls, auth: AuthSchema, hospital_id: int, template_code: str
    ) -> list[dict]:
        """将模板规则应用到指定医院（全量替换）。

        M3 注册联动会用此方法；M2 也单独暴露为 API 供手动应用模板。
        """
        hospital = await cls._ensure_hospital_exists(auth, hospital_id)

        # 校验状态允许编辑映射（LIVE 需先下线）
        from .service import HospitalService
        await HospitalService.assert_can_edit_mapping(hospital)

        template = get_template(template_code)
        if not template:
            raise CustomException(
                msg=f"映射模板不存在: {template_code}", code=404, status_code=404
            )

        # 构造批量入参并复用 replace_service
        from .schema import MappingRuleBatch, MappingRuleIn

        rules = [
            MappingRuleIn(
                src_table=r["src_table"],
                src_field=r["src_field"],
                tgt_table=r["tgt_table"],
                tgt_field=r["tgt_field"],
                transform_type=r["transform_type"],
                transform_value=r.get("transform_value"),
                description=r.get("description"),
                sort=r.get("sort", 0),
            )
            for r in template["rules"]
        ]
        batch = MappingRuleBatch(rules=rules)
        log.info(f"医院[{hospital_id}]应用模板[{template_code}]，共 {len(rules)} 条规则")
        return await cls.replace_service(auth, hospital_id, batch)

    @classmethod
    async def list_templates_service(cls, auth: AuthSchema) -> list[dict[str, Any]]:
        """列出所有可用映射模板。"""
        return list_templates()

    @classmethod
    async def get_template_service(
        cls, auth: AuthSchema, template_code: str
    ) -> dict[str, Any]:
        """查看某模板详情（含规则）。"""
        template = get_template(template_code)
        if not template:
            raise CustomException(
                msg=f"映射模板不存在: {template_code}", code=404, status_code=404
            )
        return {
            "code": template_code,
            "name": template["name"],
            "description": template["description"],
            "rule_count": len(template["rules"]),
            "rules": template["rules"],
        }

    @classmethod
    async def _ensure_hospital_exists(cls, auth: AuthSchema, hospital_id: int) -> HospitalModel:
        """校验医院存在，返回医院对象；不存在抛 404。"""
        from .model import HospitalModel
        hospital = await HospitalCRUD(auth).get_by_id_crud(id=hospital_id)
        if not hospital:
            raise CustomException(msg="医院不存在", code=404, status_code=404)
        return hospital
