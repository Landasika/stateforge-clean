# StateForge 最终验收靶标

本文指定以下 3 个 Python Web 应用作为 StateForge 最终验收靶标。验收范围覆盖 Token 认证、Session 认证、数据库状态、资源所有权、角色权限和业务状态机。

## 1. VAmPI

- 仓库：https://github.com/erev0s/VAmPI
- 框架：Flask 2.2 + connexion + SQLAlchemy
- 数据库：SQLite
- 应用类型：OWASP 漏洞 Web API 基准
- 路由数量：14
- vendored 源目录：`targets/vampi/app`
- vendored 静态观测：33 个函数、290 个 basic block、332 条边
- 状态域：Token、DATABASE

跨请求守卫：

- `POST /users/v1/login` 签发 JWT；`GET /me`、`POST /books/v1`、邮箱/密码修改接口消费 token；含 TTL 校验。
- `POST /users/v1/register` 写入用户；`GET /users/v1/{username}` 按用户存在性返回结果，属于 BOLA 测试面。
- `POST /books/v1` 写入用户书籍；`GET /books/v1/<title>` 同时检查 token 与书目存在性。
- `GET /createdb` 执行 drop/create/seed，可作为每次运行的状态重置入口。

验收用途：

- Token 认证 + 数据库资源所有权。
- 短跨请求链：`register → login → create book → read book`。
- 对象级授权和资源存在性分支。
- 用于 M2 predicate/branch flip 与 M3 constraint mutation 验收。

## 2. PyGoat

- 仓库：https://github.com/adeyosemanputra/pygoat
- 框架：Django 4.2 + django-allauth
- 数据库：SQLite
- 应用类型：OWASP 漏洞 Web 教学平台
- 路由数量：24
- vendored 源目录：`targets/pygoat/src`
- vendored 静态观测：152 个函数、1145 个 basic block、1280 条边
- 状态域：Session、DATABASE

跨请求守卫：

- `GET /auth_lab/login` 检查凭据；受保护 lab 视图依赖已建立的会话；`/auth_lab/signup` 写入 `UserInfo`。
- 各挑战视图读取/写入 `UserInfo` 中的 lesson 完成状态；跨请求完成后影响仪表盘渲染。
- `ba_lab` 使用角色门；非特权用户访问受限视图，属于 Broken Access Control 测试面。
- `/accounts/login/` 与 `/accounts/signup/` 由 django-allauth 提供同族会话门。

验收用途：

- Session 认证 + 数据库挑战状态累积。
- 角色权限分支和多类漏洞入口。
- 跨请求状态从注册/登录到 challenge 完成的变化。
- 用于 M3 predicate/constraint 与 M4 状态序列验收。

## 3. django-oscar sandbox

- 仓库：https://github.com/django-oscar/django-oscar
- 框架：Django + django-oscar
- 数据库：SQLite（sandbox 配置）
- 应用类型：生产级电商框架官方 sandbox
- 路由数量：24
- vendored 源目录：`targets/oscar/src/oscar`、`targets/oscar/sandbox`
- vendored 静态观测：2195 个函数、12447 个 basic block、12278 条边
- 冒烟观测：24/24 路由返回非 5xx；其中 302 重定向 17 个、404 共 6 个、admin 返回 200
- 状态域：Session、DATABASE、权限

跨请求守卫：

- 账户登录门：checkout、dashboard 等视图使用 `login_required`；未登录重定向到 `/accounts/login/`。
- 订单状态机：`POST /basket/add/<product>` 写入 basket；shipping address、payment details、order placement 依次消费 basket 和地址/支付状态。
- 权限门：`/dashboard/*` 依赖 staff 和 partner 关联；非 staff 返回 302。
- 目录可见性：`product.is_public` 与 stockrecord 库存状态影响商品和结算路径。

验收用途：

- Session + 数据库 + 权限三类状态组合。
- 订单生命周期：`catalogue → basket → shipping → payment → order`。
- 多步业务状态链和资源可见性约束。
- 用于 M4 跨请求状态定向测试验收。

## 验收靶标覆盖矩阵

| 维度 | VAmPI | PyGoat | django-oscar sandbox |
| --- | --- | --- | --- |
| Python Web | 是 | 是 | 是 |
| Token 认证 | 是 | 否 | 否 |
| Session 认证 | 否 | 是 | 是 |
| 数据库状态 | 是 | 是 | 是 |
| 资源所有权 | 是 | 部分 | 是 |
| 角色权限 | 管理员 | 是 | staff/partner |
| 多步业务状态 | 短链 | 中链 | 订单长链 |
| SQLite 进程内运行 | 是 | 是 | 是 |
| 已知漏洞基准 | 是 | 是 | 否 |
| 状态重置入口 | `/createdb` | 每进程 SF_DB | 每进程 SQLite |

## 验收前提

每个靶标进入验收前必须满足：

1. 在进程内通过 `test_client` 启动，每个进程使用独立 SQLite 数据库。
2. `build_icfg` 能生成非零 basic block 和边。
3. 至少登记两个跨请求守卫实例，包含生产者、消费者和状态谓词。
4. 能选定一个 basic block 作为定向目标，并保存可重放的命中输入或请求序列。
5. 保存目标 ID、源码哈希、随机种子、执行预算和状态重置方式。
6. 记录静态分析规模、动态映射失败数、覆盖块数和目标命中结果。

## 当前接入状态

- 三个靶标源码、harness、fuzz_target、requirements 和 license 已进入 `feature/m2-constraint-guidance` 分支的 `targets/` 目录。
- `main` 分支当前只包含本 docs 目录，不包含 `targets/`。
- 三个 harness 冒烟结果：VAmPI 14/14 non-5xx，PyGoat 24/24 non-5xx，Oscar 24/24 non-5xx。
- 三个靶标的 vendored 源码均已通过 `build_icfg`，basic block 数量分别为 290、1145、12447。
- 三个靶标尚未在 `feature/m2-constraint-guidance` 分支完成 M2/M4 验收运行。

## 运行入口

```text
targets/vampi/harness.py
targets/vampi/fuzz_target.py
targets/pygoat/harness.py
targets/pygoat/fuzz_target.py
targets/oscar/harness.py
targets/oscar/fuzz_target.py
targets/manifest.json
```

目标依赖分别记录在：

```text
targets/vampi/requirements.txt
targets/pygoat/requirements.txt
targets/oscar/requirements.txt
```
