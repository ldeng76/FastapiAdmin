"""插入仪表板菜单项（直接 SQL，绕过 psql 编码问题）。"""
import asyncio
import uuid
from datetime import datetime

import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://lnrs:lnrs_pwd@127.0.0.1:5432/postgres")
    # 检查是否已存在
    existing = await conn.fetchval(
        "SELECT id FROM sys_menu WHERE route_path = 'dashboard' AND component_path = 'module_medical/dashboard/index'"
    )
    if existing:
        print(f"菜单已存在 (id={existing})，跳过")
    else:
        now = datetime.now()
        await conn.execute(
            """INSERT INTO sys_menu
            (parent_id, name, type, icon, "order", permission, route_name, route_path,
             component_path, status, keep_alive, hidden, always_show, title, affix,
             description, uuid, created_time, updated_time, is_deleted, tenant_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
             $16, $17, $18, $19, $20, $21)""",
            201, "数据概览", 2, "ri:dashboard-line", 0,
            "module_medical:stats:query", "MedicalDashboard", "dashboard",
            "module_medical/dashboard/index", "0", True, False, False,
            "数据概览", False, "医疗数据概览仪表板（ETL2 脱敏数据）",
            str(uuid.uuid4()), now, now, False, 1,
        )
        print("菜单插入成功")
    await conn.close()


asyncio.run(main())
