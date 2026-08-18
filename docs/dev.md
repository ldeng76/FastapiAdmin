## 已发现的严重泄露

> **关于占位符**：本文与 `docs/敏感环境变量与配置项审计.md` 内容重叠；入库前同样把所有可被直接利用的
> 真实值（GitLab PAT、PostgreSQL 超管/应用口令、生产 IP、默认 JWT/HMAC 密钥、docker 默认口令等）
> 替换为占位符，仅保留位置、风险说明与修复建议。

```text
   GitLab 私有令牌
     - deploy-ci.sh:23（占位符 <GITLAB_PAT>，原值前缀 glpat-）
     - 已进入 Git 历史。应立即吊销并轮换，改用受保护、Masked 的 CI 变量或 Deploy Key。
   数据库与 Redis 口令
     - backend/env/.env.h125:32 （占位符 <APP_PWD_H125>）
     - backend/env/.env.h42:32   （占位符 <APP_PWD_H42>）
     - docker/.env:2            （占位符 <MYSQL_ROOT_PASSWORD>）
     - docker/.env:5            （占位符 <MYSQL_PASSWORD>）
     - docker/.env:9            （占位符 <REDIS_PASSWORD>）
     - docker/lnrs-dev.yaml:15
     - scripts/migrate_dev_to_h42.sh:18 （占位符 <SUPER_PWD>）
     - scripts/migrate_dev_to_h42.sh:20 （占位符 <APP_PWD>）
     - docs/database_migration_dev_to_h42.md:17
     - 上述文件均已被 Git 跟踪或进入历史，相关账户应按“已泄露”处理并轮换。
   JWT 签名密钥
     - SECRET_KEY 硬编码于 backend/app/config/setting.py:67 （占位符 <DEFAULT_SECRET_KEY>）
     - 实际用于签发、验证 JWT：backend/app/core/security.py:109、backend/app/core/security.py:133
     - 当前生产配置文件未覆盖它；若服务器环境也未注入，攻击者可伪造任意用户/管理员令牌。
   医学脱敏 HMAC 密钥
     - LNRS_ANON_SECRET 存在公开默认值：backend/app/config/setting.py:244 （占位符 <DEFAULT_LNRS_ANON_SECRET>）
     - 生产配置未见覆盖。该值泄露会削弱 anon_id、anon_exam_id 的不可关联性。
     - 轮换时必须配合 LNRS_ANON_SECRET_VERSION 和数据迁移方案。
   固定种子账户口令
     - backend/app/scripts/data/sys_user.json:5
     - backend/app/scripts/data/sys_user.json:26
     - backend/app/scripts/data/sys_user.json:47
     - 三个账户使用相同哈希，已验证对应项目文档公开的弱默认口令。生产初始化后必须强制随机密码或首次登录修改。

   必须作为秘密注入的变量

   - SECRET_KEY
   - DATABASE_PASSWORD
   - MYSQL_ROOT_PASSWORD
   - MYSQL_PASSWORD
   - POSTGRES_PASSWORD
   - REDIS_PASSWORD
   - REDIS_URL（完整 URL 会包含口令）
   - OPENAI_API_KEY
   - OAUTH_GITHUB_CLIENT_SECRET
   - OAUTH_GITEE_CLIENT_SECRET
   - OAUTH_WECHAT_OPEN_APP_SECRET
   - OAUTH_QQ_APP_SECRET
   - LNRS_ANON_SECRET
   - CI/CD Token、Deploy Token、私钥、证书私钥

   目前未发现真实的 OpenAI/OAuth 密钥或项目私钥文件。

   额外发现

   - 操作日志未做脱敏，直接保存表单、JSON 请求和 JSON 响应：
     - backend/app/core/router_class.py:75
     - backend/app/core/router_class.py:84
     - backend/app/core/router_class.py:100
     - backend/app/core/router_class.py:145
   - 登录和用户路由均启用该日志：auth/controller.py:43、user/controller.py:30。因此登录密码、改密字段、访问令牌和刷新令牌可能已写入操作日志数据库，应排查并清理历史记录。
   - error.log 启用了 diagnose=True：backend/app/core/logger.py:181-191，异常堆栈可能输出局部变量；生产应关闭。
   - backend/lnrs_migration_20260725_083559.pdump 当前未跟踪但也未被忽略，可能包含患者数据、密码哈希和操作日志，严禁提交。
   - .dockerignore:18 只忽略 .env，没有覆盖 .env.prod 等变体；建议同时忽略 **/.env* 和 *.pdump。
   - VITE_LOCK_ENCRYPT_KEY 会进入浏览器包：frontend/web/src/components/layouts/fa-screen-lock/index.vue:165。它不是秘密，只能提供混淆，绝不能把任何真正密钥放进 VITE_*。

   建议处理顺序：**立即吊销 GitLab Token → 轮换数据库/Redis/JWT/脱敏密钥 → 排查操作日志 → 清理 Git 跟踪与历史 → 完善 .gitignore/.dockerignore。**本次仅审计，未修改文件。

```

## 一些重要信息：
### 测试用 rustfs :
```text

cat /home/dzy/.config/rclone/rclone.conf                                                                                                                                                                                                                                                                                                          
                                                                                                                                                                                                                                                                                                                                                     
 [rustfs]                                                                                                                                                                                                                                                                                                                                            
 type = s3                                                                                                                                                                                                                                                                                                                                           
 env_auth = false                                                                                                                                                                                                                                                                                                                                    
 access_key_id = rustfsadmin01                                                                                                                                                                                                                                                                                                                       
 secret_access_key = rustfsadmin01_secret                                                                                                                                                                                                                                                                                                            
 endpoint = http://127.0.0.1:9000                                                                                                                                                                                                                                                                                                                    
 region = us-east-1                                                                                                                                                                                                                                                                                                                                  
 provider = Other                           
 
```
