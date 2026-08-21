# Green Finance 向量数据库与知识图谱部署交接

本文给绿色金融下游团队使用。目标是在现有广州服务器上运行团队自己的向量数据库
和知识图谱，同时不取得数据中心、OpenClaw 或 Science Workshop 的管理权限。

## 0. 账号已开通

2026-08-20 已完成服务器账号、公钥、rootless Podman、独立磁盘和资源限制配置：

```text
ACCESS_READY
HOST=106.53.153.215
USER=greenfinance-vector
LOGIN=ssh greenfinance-vector@106.53.153.215
WORKDIR=/srv/green-finance-vector
SSH_HOST_ED25519_SHA256=yA0y7TrY627Xav6sh0wYM+zoOOsulj7UdahAcsvtYdM
AUTHORIZED_KEY_SHA256=boT+x6co3RAmnPpX5lKNlIO42kgnGc8mHupARmQQw8w
```

已绑定的公钥注释为 `dgcrdeyouxiang@163.com`。私钥仍只保存在使用者自己的电脑上；
管理员没有私钥，也不会通过聊天索取私钥、密码、CAM SecretKey 或数据库密码。

如需更换电脑或轮换公钥，先生成新的 Ed25519 公钥并把 `.pub` 文件内容交给管理员；
旧公钥应在新公钥实际登录成功后再撤销。

## 1. 已有账号与权限边界

腾讯云 CAM 子账号是 `green-finance-reader`。它继续只关联
`GreenFinanceCOSReader`，用于列举和下载 `green-finance-handoff/`；不能上传、
覆盖或删除 COS 对象，也不能读取 `green-finance-backups/`。

这个 CAM 账号不用于服务器运维。不要为它增加 Lighthouse 全部操作、自动化助手
任意命令、重置密码、重装系统、修改防火墙或 `green-finance-publisher` 权限。
Lighthouse/自动化助手命令以 root 身份执行，给出这类权限就等于把共享服务器、
生产数据和另外两个项目一并交出，无法实现项目级隔离。

服务器部署使用独立 Linux 账号 `greenfinance-vector`。截至 2026-08-20 已按以下边界
开通并验证：

- 无 `sudo`，不属于 `docker` 组；
- 项目持久数据只能写入自己的家目录 `/srv/green-finance-vector/`；系统临时目录仅作
  临时文件使用；
- 使用 rootless Podman/Compose 管理自己的容器；
- Qdrant 和 Neo4j 只监听 `127.0.0.1`，通过 SSH 隧道访问；
- 不能读取 `/etc/green-finance/`、`/opt/green-finance/`、生产 PostgreSQL、
  OpenClaw、Science Workshop 或 COS 灾备。

## 2. 当前服务器条件

2026-08-20 实际部署与验收结果：

- 实例：广州 `lhins-rqikvtij`，Ubuntu Server 24.04 LTS；
- 配置：2 核、8 GB 内存、120 GB 系统盘；
- 验收时可用内存约 6.1 GiB，根盘可用约 85 GB；
- 已安装 Podman `4.9.3`、podman-compose `1.0.6`，并验证为 rootless；
- 独立挂载 `/srv/green-finance-vector`，可用容量约 39.1 GiB；
- Green Finance API 保持 `active`，健康检查为 `status=ok`；
- `6333`、`6334`、`7474`、`7687` 验收时均未监听；
- 云防火墙已开放 SSH 22；不得再开放上述数据库端口。

这是共享主机，只适合有硬上限的单机试运行。账号已设置 1.5 CPU、3 GiB 内存软上限、
3.5 GiB 内存硬上限、640 个任务和约 40 GB 独立持久盘；宿主机可用内存持续低于
2 GiB 时停止扩容，改用独立实例。

## 3. 首次登录

Windows PowerShell、macOS 终端或 Linux 终端执行：

```bash
ssh greenfinance-vector@106.53.153.215
id
podman --version
podman-compose version
systemctl --user status
```

首次连接会显示服务器 Ed25519 主机指纹。只有当 SHA-256 指纹严格等于
`SHA256:yA0y7TrY627Xav6sh0wYM+zoOOsulj7UdahAcsvtYdM` 时才接受；不一致时立即停止并
联系管理员。

如果本地直连 SSH 不稳定，只报告完整报错和来源公网 IP；不要要求开放 Qdrant、
Neo4j 或 Docker 的公网端口，也不要重置服务器 root 密码。

推荐目录：

```text
/srv/green-finance-vector/
├── deploy/              # compose.yaml 与部署说明
├── input/               # 已校验的数据中心 release
├── qdrant/              # Qdrant 配置、快照说明
├── neo4j/               # Neo4j 导入、dump 说明
├── backups/             # 团队自己的有界备份
└── .env                 # 0600，仅服务器本地
```

## 4. 数据输入

登录服务器后优先使用本机只读 Feed，不需要 PostgreSQL 或 COS 权限：

```bash
curl -fsS http://127.0.0.1:4173/api/feed
curl -fsS 'http://127.0.0.1:4173/api/feed/articles?scope=green&limit=500'
```

2026-08-20 已用 `greenfinance-vector` 实测上述两个接口均返回 HTTP 200。服务器当时
访问 Vercel 公网域名的 443 端口超时，因此服务器定时任务不要依赖公网域名。

从自己的电脑读取公开数据时仍可使用：

```bash
curl -fsS https://green-finance-dashboard.vercel.app/api/feed
curl -fsS 'https://green-finance-dashboard.vercel.app/api/feed/articles?scope=green&limit=500'
```

无论使用本机还是公网入口，完整分页都必须保存第一次响应的 `snapshot_at` 和
`dataset_version`，使用同一个 `until=<snapshot_at>` 读取到 `next=null`，再读取
一次 `/api/feed`。只有前后 `dataset_version` 相同才接受这批数据。每日增量及重试规则见
[`METADATA_FEED.md`](METADATA_FEED.md)。

需要获准全文时，使用已有的 `green-finance-reader` 编程凭据下载私有 COS release：

```bash
export COS_SECRET_ID='<reader SecretId>'
export COS_SECRET_KEY='<reader SecretKey>'
export COS_BUCKET='<private bucket name>'
export COS_REGION='ap-guangzhou'
export COS_PREFIX='green-finance-handoff'
npm ci
npm run handoff:download -- --output-dir /srv/green-finance-vector/input
unset COS_SECRET_ID COS_SECRET_KEY
```

SecretId/SecretKey 只放在权限为 `0600` 的服务器本地凭据文件或进程环境中，不写入
Git、compose 文件、聊天或部署文档。每次入库前保留 `latest.json`、
`manifest.json` 和各文件 SHA-256；完整契约见 [`VECTOR_HANDOFF.md`](VECTOR_HANDOFF.md)。

## 5. 首版容器配置

首版使用 Qdrant `v1.18.2-unprivileged` 和 Neo4j Community `2026.06.0`。部署前把
镜像解析为团队记录过的 digest；升级版本时另开变更，不使用浮动 `latest`。

在 `deploy/compose.yaml` 写入：

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.18.2-unprivileged
    restart: unless-stopped
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
      QDRANT__SERVICE__READ_ONLY_API_KEY: ${QDRANT_READ_ONLY_API_KEY}
    volumes:
      - qdrant-data:/qdrant/storage
      - qdrant-snapshots:/qdrant/snapshots
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    mem_limit: 1536m
    cpus: 0.75
    pids_limit: 256

  neo4j:
    image: neo4j:2026.06.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_server_memory_heap_initial__size: 512m
      NEO4J_server_memory_heap_max__size: 512m
      NEO4J_server_memory_pagecache_size: 512m
      NEO4J_server_jvm_additional: -XX:+ExitOnOutOfMemoryError
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
      - neo4j-import:/import
    security_opt:
      - no-new-privileges:true
    mem_limit: 2g
    cpus: 0.75
    pids_limit: 384

volumes:
  qdrant-data:
  qdrant-snapshots:
  neo4j-data:
  neo4j-logs:
  neo4j-import:
```

在服务器本地生成凭据，不把生成值打印到聊天或 Git：

```bash
cd /srv/green-finance-vector/deploy
umask 077
QDRANT_API_KEY="$(openssl rand -hex 32)"
QDRANT_READ_ONLY_API_KEY="$(openssl rand -hex 32)"
NEO4J_PASSWORD="$(openssl rand -hex 24)"
printf 'QDRANT_API_KEY=%s\nQDRANT_READ_ONLY_API_KEY=%s\nNEO4J_PASSWORD=%s\n' \
  "$QDRANT_API_KEY" "$QDRANT_READ_ONLY_API_KEY" "$NEO4J_PASSWORD" > .env
unset QDRANT_API_KEY QDRANT_READ_ONLY_API_KEY NEO4J_PASSWORD
chmod 600 .env
```

启动并验证：

```bash
podman-compose pull
podman-compose up -d
podman-compose ps
set -a; . ./.env; set +a
curl -fsS -H "api-key: $QDRANT_API_KEY" http://127.0.0.1:6333/collections
podman-compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  'RETURN 1 AS ok;'
unset QDRANT_API_KEY QDRANT_READ_ONLY_API_KEY NEO4J_PASSWORD
```

从自己的电脑访问时建立隧道：

```bash
ssh \
  -L 4173:127.0.0.1:4173 \
  -L 6333:127.0.0.1:6333 \
  -L 7474:127.0.0.1:7474 \
  -L 7687:127.0.0.1:7687 \
  greenfinance-vector@106.53.153.215
```

随后本地可以访问 `http://127.0.0.1:4173/api/feed`、
`http://127.0.0.1:6333/dashboard` 和 `http://127.0.0.1:7474`。不要申请公网开放
`4173`、`6333`、`6334`、`7474` 或 `7687`。

## 6. 增量、备份和验收

- `article_id` 是源记录主键；另行持久化
  `article_id -> canonical_document_id`，不要按标题直接删除或合并。
- `content_hash` 变化才重新清洗、切块和 embedding；`metadata_hash` 变化只更新
  元数据或过滤索引。
- 原始 release、清洗代码版本、embedding 模型版本、切块参数和图谱规则版本必须
  与每次入库结果一起保存。
- Qdrant 使用快照，Neo4j Community 使用停机 dump；备份写入团队自己的
  `backups/`，设置条数或字节上限，不写数据中心的 COS 备份前缀。
- 验收时确认四个数据库端口仍只绑定 `127.0.0.1`，并检查容器内存、磁盘、重启
  状态和一次完整检索/查询。

## 7. 需要管理员处理的事项

下面任何一项都不要自行绕过：

1. 首次开通或轮换 SSH 公钥；
2. 安装/升级 rootless Podman 或 Compose provider；
3. 调整 CPU、内存、磁盘上限；
4. 修改云防火墙、Nginx、systemd 或宿主机目录权限；
5. 需要公网服务、域名、TLS 或新的腾讯云资源；
6. 需要读生产 PostgreSQL、写 COS 或访问灾备。

申请时给出用途、准确端口/目录、预计峰值 CPU/内存/磁盘、回滚方法和所需时限。

## 参考

- [腾讯云轻量应用服务器子账号权限管理](https://cloud.tencent.com/document/product/1207/107493)
- [腾讯云 COS 最小权限原则](https://cloud.tencent.com/document/product/436/38618)
- [Qdrant Security](https://qdrant.tech/documentation/security/)
- [Neo4j Docker 部署](https://neo4j.com/docs/operations-manual/current/docker/introduction/)
- [Neo4j 内存配置](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
