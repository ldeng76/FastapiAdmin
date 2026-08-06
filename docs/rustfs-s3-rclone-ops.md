# RustFS + rclone 运维速查（196.4）

> 部署目标：`10.12.196.4`（database-1），单节点单盘（SNSD）模式。
> 本文档供后续人工运维速查，覆盖 RustFS 服务、S3 接口、rclone 客户端三部分。

---

## 1. RustFS 对象存储服务

### 基本信息

| 项 | 值 |
|---|---|
| 二进制 | `/usr/local/bin/rustfs`（1.0.0-beta.12，musl 静态构建） |
| systemd 服务 | `rustfs.service`（enabled，开机自启） |
| 配置文件 | `/etc/default/rustfs`（600 权限） |
| 数据目录 | `/data2/rustfs0`（单盘 = SNSD） |
| S3 服务端口 | 9000 |
| 控制台端口 | 9001（需认证） |
| 逻辑日志 | `/var/log/rustfs/` |

### 服务管理

```bash
sudo systemctl status rustfs      # 状态
sudo systemctl restart rustfs     # 重启
sudo journalctl -u rustfs -n 100  # 看日志
```

### 凭据

配置在 `/etc/default/rustfs`：

```
RUSTFS_ACCESS_KEY=rustfsadmin01
RUSTFS_SECRET_KEY=rustfsadmin01_secret
RUSTFS_VOLUMES="/data2/rustfs0"
RUSTFS_ADDRESS=":9000"
RUSTFS_CONSOLE_ADDRESS=":9001"
RUSTFS_CONSOLE_ENABLE=true
```

> 修改凭据：编辑该文件后 `sudo systemctl restart rustfs`。
> 注意：脚本显式禁止使用 `rustfsadmin` 作为默认凭据值。

### 运维 CLI（rustfs 自带）

```bash
rustfs info        # 系统信息
rustfs diagnose    # 分析日志、诊断可能故障原因
rustfs tls         # 检查 TLS 证书目录布局与解析状态
rustfs server      # 启动服务（无子命令时默认动作，一般由 systemd 管理）
```

`rustfs` 不提供 S3 客户端命令；对象读写走标准 S3 API（用 rclone 等客户端）。

---

## 2. rclone S3 客户端

### 基本信息

- **rclone v1.75.0**（静态二进制）→ `/usr/local/bin/rclone`
- 配置文件：`/home/dzy/.config/rclone/rclone.conf`（600 权限）
- remote 名：`rustfs`，指向本机 `http://127.0.0.1:9000`

### 已配置 remote

```ini
[rustfs]
type = s3
access_key_id = rustfsadmin01
secret_access_key = rustfsadmin01_secret
endpoint = http://127.0.0.1:9000
region = us-east-1
provider = Other
```

> rclone 走本机 `127.0.0.1:9000`，**不依赖外网隧道**，日常备份/上传与 `net-on` 隧道状态无关。

### 命令速查

```bash
rclone lsd rustfs:                        # 列桶
rclone ls rustfs:BUCKET                   # 列对象
rclone tree rustfs:                       # 树状浏览全部

rclone mkdir rustfs:buck1                 # 建桶
rclone rmdir rustfs:BUCKET                # 删空桶
rclone purge rustfs:BUCKET                # 删桶及全部内容（慎用）

rclone copyto 本地文件 rustfs:BUCKET/key     # 上传单个文件（自动建桶/目录）
rclone copyto rustfs:BUCKET/key 本地路径      # 下载单个对象
rclone copy 本地目录 rustfs:BUCKET/          # 上传目录（增量）
rclone copy rustfs:BUCKET/ 本地目录          # 下载目录（增量）
rclone sync 本地目录 rustfs:BUCKET/          # 单向同步到远端（目标多出的会被删除）
rclone deletefile rustfs:BUCKET/key        # 删除单个对象
```

### 已创建桶

- `buck1`（空桶，通过 `rclone mkdir rustfs:buck1` 创建）

---

## 3. 相关背景

- RustFS 安装脚本：`https://github.com/rustfs/rustfs.com/blob/main/public/install_rustfs.sh`
  - 默认数据目录 `/data/rustfs0`；本机按需使用 `/data2/rustfs0`。
  - 脚本下载走 `dl.rustfs.com`；198.4 无直连外网，需经 SOCKS5 隧道（`net-on` → 127.0.0.1:1080）拉包。
  - 脚本按 glibc 版本选包：GNU 包需 GLIBC≥2.38，而 196.4 是 glibc 2.35，**必须用 musl 静态包**（`rustfs-linux-x86_64-musl-latest.zip`）。
- SOCKS5 上网隧道（可选外网通道，与 RustFS/rclone 无关）：`net-on` / `net-off` / `net-status`（定义于 `/etc/profile.d/socks5-tunnel.sh`）。
