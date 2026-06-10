# lnrs

<div align="center">
     <p align="center">
          <img src="frontend/web/public/logo.svg" width="150" height="150" alt="logo" />
     </p>
     <h1>肺结节研究系统 <sup style="background-color: #28a745; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.4em; vertical-align: super; margin-left: 5px;">v1.0.1</sup></h1>
     <h3>🚀 基于 FastAPI + Vue3 + TypeScript 的肺结节研究管理系统</h3>
     <p>基于 <b>FastAPI + Vue3 + TypeScript</b> 的全栈快速开发平台</p>
</div>

## 💡 系统介绍

肺结节研究系统是一款面向医学研究的专业后台管理系统，提供完善的用户权限管理、数据分析等功能。

## 🚀 快速启动

### 环境要求

| 环境要求 | |
|---------|------|
| Python ≥ 3.10（推荐 3.12） | Node.js ≥ 20.0 + pnpm |
| MySQL 8.0+ / PostgreSQL 14+ | Redis 6.x / 7.x |

### 启动步骤

```bash
# 1. 克隆
git clone http://hermes2026git.nmdi.cn/lnrs/lnrs_web.git

# 2. 配置后端环境
cd backend
cp env/.env.dev.example env/.env.dev
uv sync && uv run main.py run --env=dev

# 3. 启动前端
cd ../frontend/web && pnpm install && pnpm run dev

# ✅ 浏览器打开 http://127.0.0.1:5610，用 admin/123456 登录
```

## 📦 工程结构

```
lnrs/                 # 全栈工程
├─ backend/           # FastAPI 后端
├─ frontend/
│   └── web/          # Vue3 Web 前端
├─ docker/            # Docker 部署配置
└─ deploy.sh          # 一键部署脚本
```

## 📖 文档

- 🌐 详细开发指南请参考项目内各模块 README