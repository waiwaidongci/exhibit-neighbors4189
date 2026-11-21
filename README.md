# 苇谱展陈偏好配对册

用户均值中心化相似邻居协同过滤与留一评分RMSE。为苇谱研究协作组的12位分析与业务人员提供从样本核对、独立worker计算到批准快照交付的完整工作流。

## 真实业务场景

匿名试展显式评分→邻居推荐与冷启动说明→策展备选；仅使用训练评分，相似度共同评分阈值。团队原先将 `exhibit-neighbors-202611-01.csv` 复制到多份人工表格，复核时再逐项对照。三个痛点是口径不可追溯、重复计算易错、业务说明与结果脱节。上游提供合成业务观察，系统承担研究和复核，下游业务人员读取批准快照。全部演示数据是固定随机种子生成的模拟数据。

## 业务模块

1. 业务总览：批次、样本、任务与批准交付账册。
2. 试展评分册：创建/修改来源说明、查看样本、用真实业务字段追加记录；列表分页。
3. 分析配置：冻结来源、参数和全部样本，进入Redis队列。
4. 完整结果：真实算法摘要、专属诊断、全部CSV导出和可恢复失败态。
5. 策展备选：分析师草案→负责人批准→阅读者下载批准快照。
6. 迁展演练：封存原册→换匿名号评分副本→最少原配对复用→对账→整批开放研究选用。
7. 审计：登录、来源修改、任务worker完成、业务说明批准、演练封存与开放等事件。

## 快速启动

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
# 可重复执行，不覆盖人工修改
docker compose exec -T backend python -m scripts.seed_demo
```

访问 [前端](http://localhost:18249)；[API文档](http://localhost:19249/docs)。数据库仅演示用途映射 `17749`。首次准备依赖和初始化数据库需要等待健康状态：`docker compose ps`，五个服务均需healthy。

| 组件 | 技术与职责 |
|---|---|
| frontend | 原生 HTML / CSS / JS ES Modules，Nginx代理 `/api/` |
| backend | Python3.11 / FastAPI / SQLAlchemy / JWT |
| worker | 独立Python进程，Redis BLPOP队列，持久化结果/CSV/心跳 |
| db | MySQL8，命名卷持久化 |
| redis | Redis7，AOF命名卷 |

恰好五服务，均配置healthcheck；后端/worker依赖数据库与Redis健康，前端依赖后端健康；worker与后端共享 `artifacts` 命名卷。重置演示环境：`docker compose down -v --remove-orphans`，会删除本项目卷。

## 账号与权限

所有演示账号密码：`Research2026!`。

| 邮箱 | 角色 | 权限 |
|---|---|---|
| admin@exhibit-neighbors.demo | admin | 全部录入/执行、批准业务说明 |
| analyst@exhibit-neighbors.demo | analyst | 录入来源/样本、执行、提交说明，无批准权 |
| viewer@exhibit-neighbors.demo | viewer | 只读、导出结果及已批准快照 |

时间在数据库/API中以UTC存储，总览与审计页面明确转换为Asia/Shanghai北京时间。

JWT有效期8小时；PBKDF2盐化哈希保存密码；角色每请求从数据库读取。访客写操作403，匿名访问业务数据401，重复样本409，非法业务字段422，重复批准409。每客户端/路径写请求90次/分钟，超限429。生产使用需修改JWT及演示数据库凭据。

## 实体与字段

Exhibition / VisitorRating / RecommendationRun / CuratorSelection 是核心实体；另有User和Audit。数据库实际表：`exhibitions` → `visitor_ratings` → `recommendation_runs` → `curator_selections`。迁展演练另用 `drill_jobs`（封存快照、换号结果、对账与开放状态）与 `drill_ratings`（换号副本，`(job_id,anon_id,exhibit)` 唯一）。样本以固定字段JSON保存，后端按以下字段严格验证，不接受未知字段替代必填值：匿名访客（`visitor`）、展品代号（`exhibit`）、评分 1–5（`rating`）。

实体贯穿 `backend/src/models`、`schemas`、`services`、`controllers`、`routes`，以及 `frontend/src/api/research.js`、`stores/research.js` 和 `pages`。`Source.key` 与 `(Record.source_id, reference)` 为自然键；来源改名不会修改已冻结任务输入。业务说明在创建时保存结果快照，批准后从该快照导出。

## 算法与口径

用户均值中心化相似邻居协同过滤与留一评分RMSE，全部计算位于 `backend/src/services/algorithm.py`，前端不拟合模型、不生成模拟结果。输入是冻结业务观察及参数，输出summary、专属诊断、逐行计算明细、seed与输入SHA256。CSV包含全部结果行；页面仅预览前30行。参数：

- `neighbors`：相似邻居上限，默认 `5`。
- `min_common`：共同评分下限，默认 `2`。

访客均值中心化的余弦相似度，仅使用正相似邻居；每位访客留一评分验证，留出评分不进入训练。无邻居时回退展品均值。

失败态：业务字段缺失/非有限数值、参数越界、样本不足、退化特征或结构错误均明确拒绝或将任务标failed，错误消息保存在任务中。可回到来源或配置修正后重新执行，历史失败记录保留。

已知边界：显式1–5评分，不是隐式行为推荐；按展品代码确定性留一，不能当作时间外推验证。相似度只取正值，至少两个共同评分；回退会显示依据。生产建议在完成评估后用全量已知评分，不将训练评分误报验证。

## 迁展演练（换号评分副本）

迁展演练把原册评分换一套匿名编号，生成可用于研究的评分副本，全部逻辑位于 `backend/src/services/drill_core.py` 与 `services/drills.py`，前端不计算、只发起与核对。

**业务规则与封存语义**

- 受理即封存原册：保存当时已提交评分的不可变快照及 `sha256` 校验和。封存之后的并发补录仍写入活册（`visitor_ratings`），不进入该次快照，因此补录不会污染已受理演练。
- 换号是原匿名编号上的一个随机置换；副本保留**每人评分条数**与**每件展品各星级人数**，并以唯一键 `(job_id, anon_id, exhibit)` 强制**同人同展品限一条**。
- 幂等受理：`idempotency_key` 为唯一受理号，同号重复受理返回同一演练，不新增副本。
- 可恢复执行：记录 `stage`（sealed→matching→copy→reconciled）与 `attempts`。写入中断后按同一受理号沿封存版本重试；重试先清除上一轮未完成副本再整体重写，故同次重试不新增副本、不翻倍。可用环境变量 `DRILL_FAULT=stage` 注入故障演练恢复。
- 对账通过才开放：七项核对（总条数、每人条数、每展品星级直方图、配对唯一、匿名号为置换、复用数为全局最小、快照完整性）全部通过，状态才置为 `open`，整批开放给研究选用；研究副本接口只返回换号后的 `anon_id/exhibit/rating`，不回显原编号。

**最少原配对复用（不穷举，多项式时间）**

"原配对复用"指副本里某人-展品对与原册是同一对。把原册建模为二分图（人—展品边带星级），令 Z 为"非原边"子图：容量1的 `(人,展品)` 边当且仅当原册不存在该对，再以 `s→人` 容量=该人条数、`展品→t` 容量=该展品评分量，构造带度约束的二分 b-匹配。于是

```text
最少复用数 min_reused = 总评分条数 N − Z 上最大流 M
```

实现用最小费用最大流（原边费用1、非原边费用0）一次求出 `min_reused`，并用**独立的 Dinic 最大流**在同一 Z 上重算 M，再由最大流-最小割定理输出最小割容量与割边清单作为可核查的最优性下界证明：任何方案至多安排 M 条非原边，本方案恰好达到该下界，故为全局最优。两套求解器结果必须闭合，否则直接报错拒绝出副本。节点 O(P+E)、边 O(PE)，二百人规模秒级完成，不枚举任何置换或配对。证书（公式、M、割容量、割边、复杂度、seed）随演练保存并在页面展示。

**接口（前缀 `/api` 由 Nginx 代理，后端实际无该前缀）**

| 方法与路径 | 权限 | 说明 |
|---|---|---|
| `POST /drills` | 分析师/负责人 | 受理并封存原册，body 含 `name`、`idempotency_key`，返回 `created` 与任务 |
| `GET /drills` | 登录用户 | 演练列表（不含快照大字段） |
| `GET /drills/{id}` | 登录用户 | 演练详情、最优性证书与对账 |
| `POST /drills/{id}/start` | 分析师/负责人 | 发起换号副本构造（已开放则幂等返回） |
| `POST /drills/{id}/retry` | 分析师/负责人 | 中断后沿封存版本恢复，不新增副本 |
| `GET /drills/{id}/overlap` | 登录用户（仅 open） | 逐行重合数核对，含最小值与证书 |
| `GET /drills/{id}/research-copy?limit=` | 登录用户（仅 open） | 整批开放的匿名研究副本 |

状态机：`sealed`（已封存）→ `building`（构造中）→ `open`（已对账开放）；失败落 `failed`（中断待恢复），重试不改变受理号。


## 演示数据与一天剧本

固定seed=42，3个来源 ` WP-202611-01/02/03`，每来源240条，共720条业务记录；三个账号和首轮种子任务。自然键检查后仅插入缺失数据，连跑seed不重复、不覆盖用户修改。`SEED_DEMO=true` 时启动自动执行；失败记录日志但不阻塞服务。首轮任务同样由独立worker真实计算。

1. 09:00 负责人查看三份来源和720条样本。
2. 09:10 分析师选择 `WP-202611-01 秋季常规组`，核对 `exhibit-neighbors-202611-01.csv`。
3. 09:15 在“试展评分册”核对匿名访客（`visitor`）、展品代号（`exhibit`）、评分 1–5（`rating`），追加编号 `WP-NEW-001` 的样本。
4. 09:20 新建“十一月复核研究”，按默认参数冻结241条输入。
5. 09:21 独立worker消费Redis队列，返回实算结果与输入校验和。
6. 09:25 分析师查看专属诊断及逐行结果，并下载CSV复算。
7. 09:30 提交“十一月业务复核意见”，负责人核对并批准。
8. 09:40 viewer下载批准快照，查看审计中的worker完成与批准事件。

## 目录与本地开发

```text
frontend/src/api, stores, types, components/common, hooks, pages, router, utils, constants
  迁展演练：api/drills.js、stores/drill.js、pages/drill.js
backend/src/routes, controllers, services, models, schemas, middlewares, utils, constants, config
  迁展演练：routes/drills.py、controllers/drills.py、services/drills.py、services/drill_core.py、models/drill.py、schemas/drill.py
backend/scripts/seed_demo.py
backend/migrations/001_initial.sql
```

本地后端：Python3.11虚拟环境安装 `backend/requirements.txt`，设置 `DATABASE_URL`、`REDIS_URL`、`ARTIFACT_DIR`，在backend目录运行 `uvicorn src.main:app --reload`；另开终端运行 `python -m src.worker`。原生前端无需编译，推荐以Compose Nginx访问，保证 `/api/` 代理。前端为Google Fonts双字体、oklch色板，离线字体回退serif；1280/768/390响应布局。

| 环境变量 | 默认与说明 |
|---|---|
| COMPOSE_PROJECT_NAME | `exhibit-neighbors`，隔离容器/网络/命名卷 |
| FRONTEND_PORT / BACKEND_PORT / DB_PORT | `18249 / 19249 / 17749` |
| SEED_DEMO | `true` |
| JWT_SECRET | `.env.example`演示值，部署前修改 |
| DATABASE_URL / REDIS_URL | Compose内部连接，定义在compose的env锚点 |
| ARTIFACT_DIR | `/artifacts`，后端worker共享 |

共享枚举：`backend/src/constants/enums.py` 与 `frontend/src/constants/enums.js` 都定义 admin/analyst/viewer、queued/running/completed/failed、draft/approved。后端service检查对应字符串；README为全量值说明。共享前端组件table/status/chart/business跨总览、结果、配置与复核复用；actions hook和format utils负责交互/格式。后端errors与rate_limit是两个中间件。

测试及截图在批根 `test-artifacts/gb-0045/`，不混入源码。独立算法oracle、HTTP完整流程和真实Playwright浏览器流程见该目录 `TESTING.md`。License：MIT。
