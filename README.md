# 棱砂颜料光谱解混册

在固定校准端元下做非负、和为一的光谱解混，保留重建残差、可辨识性检查与条件噪声情景，再把配比交给独立复配验证。

棱砂修复材料实验室有12位材料研究员，为展陈颜料修复准备矿物小样。上游文件 `ls-pigment-spectra-202611.json` 包含400–675nm、间隔25nm的12个反射率波段。过去研究员在电子表格中按峰值估配，负配比由人工截断，复配记录另存文档；难以重现约束、误把残差当测量噪声、无法追溯批准版本。本系统替代估配和研究归档环节，下游由材料负责人批准实验计划，阅读者下载配比CSV，实验室另做称量与测谱。

## 启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

可直接在中文目录运行。前端 http://localhost:18223 ，API http://localhost:19223/docs ，MySQL localhost:17723。恰好5服务：Nginx前端、FastAPI、独立Python worker、MySQL8、Redis7；每个都有健康检查。Nginx将 `/api/` 去前缀代理到后端。数据库、Redis队列、后端与worker共享产物分别使用命名卷。`SEED_DEMO=true` 在API启动时初始化演示数据，独立seed命令可重复执行；自然键只补缺失行，不覆盖已有批注或建议。演示为本地单机配置，部署时修改JWT_SECRET和Compose内数据库口令。

| 角色 | 账号 | 密码 | 典型权限 |
|---|---|---|---|
| 材料负责人 admin | admin@lengsha.demo | Lengsha2026! | 创建研究、批注、提交建议、批准或退回 |
| 光谱研究员 analyst | analyst@lengsha.demo | Lengsha2026! | 核对来源、创建研究、编辑样本批注、提交复配建议 |
| 修复阅读者 viewer | viewer@lengsha.demo | Lengsha2026! | 查看全部页面及审计、下载获批研究CSV |

后端JWT验证角色；隐藏按钮以外，写操作真实执行403。任何认证用户可读研究；未获批研究禁止导出，完成且至少有一份获批建议才可下载。已审阅建议不可重复审批。登录IP每分钟最多30次，全局错误处理中间件统一未知异常响应，所有登录/写入/worker完成写入审计。

## 一天的工作

1. 09:00 苏砚以研究员登录，打开“端元与样本”，核对 `LS-A` 的赭石、石绿、白垩、石青12波段曲线。
2. 09:05 检查 `LS-B`：增广矩阵病态，拒绝提交，以免把不稳定配比说成唯一成分。
3. 09:10 从 `LS-A-001` 至 `LS-A-003` 选择三份混合样本，新建“首批矿物三样本复配研究”，sigma=0.005反射率、80次条件重复、根种子2026。
4. 09:11 打开“空白校准”，用同一空池、同一仪器设置的重复读数建立联合协方差校准；页面显示有效测量数与自由度。新建研究选择该空白校准而非独立sigma。
5. 09:12 独立worker从Redis取任务，读取已冻结来源快照并算支持集KKT和条件重拟合，结果可每2秒轮询。
6. 09:15 查看首样本点估计约 `[0.125327, 0.126078, 0.286521, 0.462073]`，RSS约 `0.000114999`；这些数值来自seed及真实HTTP运行，不作为前端常量。
7. 09:20 对比观测/重建谱、逐波段残差和全部条件重复。LS-C最后10份样本含线性模型外偏离；高残差仅提示检查失配。
8. 09:30 填写复配解释与验证方案，注明固定端元及噪声来源（空白联合校准或旧版sigma），提交贺青审阅。
9. 10:00 贺青批准“研究归档”，林岑以阅读者下载 `spectral-run-N.csv`，据此安排独立称量、重新测谱。批准不等于真实材料成分得到证明。

## 七页与实体

首页、端元与样本、解混配置、配比与残差、空白校准、复配审阅、研究留痕。六个业务实体 `SpectralLibrary / Endmember / MixtureSample / UnmixRun / ReplicationNote / BlankCalibration` 均具备表、model、schema、service、route、前端API、store与页面/组件；另有User/Audit。输入库/端元/观测向量在运行创建时冻结，后续批注不改历史结果。

三个库各40混合样本、4端元×12波段，共120样本/12端元。LS-A可辨识，LS-B近共线拒绝，LS-C含10份偏离线性模型样本。所有演示数据均为固定种子的合成谱，不是材料实测。真配比未提供给算法。连续标量 `noise_sigma` 使用MySQL DOUBLE，光谱/比例数组使用JSON双精度浮点，避免单精度改变输入。

## 空白测谱校准

“空白校准”页接收同一空池、同一仪器设置下的重复测谱，每行一次完整重复、按波段排列。校准规则 `blank-joint-covariance-v1` 明确：每次重复必须覆盖全部波段且为有限反射率；扣除各波段均值后估计无偏样本协方差；要求协方差满秩、条件数≤1e6、噪声RMS∈(0,0.2]。缺波段、非有限读数、重复数不足（自由度<波段数）、零方差波段、秩亏或病态协方差一律整批拒绝并显示原因，不静默退回独立等方差噪声。有效测量数是参与协方差的完整空白重复行数n，协方差自由度n−1；两者随校准一起冻结并显示，CSV也保留。

新研究冻结所用校准的规则版本、读数来源指纹与估计指纹（`source_hash`、`calibration_hash`）；规则更新后，旧研究保留原有冻结来源与算法版本，不能静默改算；新研究只能选用当前规则估计的校准，旧规则校准须先按当前规则从同一批空白读数重算（`derived_from_id` 保留谱系）。未选择校准的研究继续使用旧版独立噪声并标记为兼容路径；旧客户端省略 `noise_mode` 仍按 `noise_sigma` 默认0.005执行。已批准研究的CSV导出列包含噪声模型、校准编号与指纹、有效测量数和自由度，可追溯来源。

## 算法与边界

令A为“波段×端元”矩阵、y为混合谱，求 `min ||Aw-y||²`，满足 `w>=0, 1ᵀw=1`。限制2–6端元、2–64波段。枚举最多63个非空支持集S，对每个支持集求等式约束KKT解：

```text
[ 2 A_Sᵀ A_S   1 ] [w_S] = [2 A_Sᵀ y]
[      1ᵀ      0 ] [ ν ]   [    1    ]
```

实现用 `w=1/k+Zz`（Z为和为零空间的正交基），以SVD最小二乘解 `A_S Z z ≈ y−A_S/k`，再恢复等式KKT乘子，避免显式法方程平方条件数。筛除权重小于−1e−10或和误差大于1e−8的候选，容差内负数截0后归一，严格按实际RSS选最小，不用固定绝对RSS并列阈值。全局最优必落在某个支持集，完整枚举包含该面；最后检查完整KKT：活动梯度近0、非活动梯度非负。KKT容差为 `1e−8*(1+||A||²+||A||||y||)`，活动判定w>1e−8。页面显示活动误差，API保留等式误差/非活动松弛/容差。

唯一性先决是增广 `[A;1ᵀ]` 满列秩，允许A自身秩亏但在和约束切空间上可辨识。SVD数值秩阈值 `max(shape)*eps*s_max`；增广条件数超过1e6或秩亏拒绝运行，页面不输出貌似唯一的配比。这个阈值是明确的数值工程守卫，不是实际材料可辨识性的证明。

第二算法条件于固定A及给定噪声模型。旧版路径（兼容）每次独立生成 `y*=y+N(0,sigma² I)`；空白校准路径按冻结的跨波段协方差C生成 `y*=y+Lz`（`LLᵀ=C`），并在白化空间求解同一非负、和为一约束，等价于广义最小二乘 `min (Aw−y)ᵀC⁻¹(Aw−y)`，点估计、全部重复与分位都使用该加权目标；RSS/RMSE仍按原始反射率报告。根SeedSequence按样本自然键排序派生独立子流，保存全部重复配比/RSS；2.5/97.5%分位用线性插值。sigma取0–0.2反射率，0表示无扰动、范围退化。每次选1–6样本、20–120次，样本数×重复数≤480以限制计算量。这是给观测加噪的条件扰动情景，不是真实成分的覆盖保证，不涵盖端元校准误差、相关噪声、非线性或模型失配。高残差标记RMSE>max(3sigma或3·空白噪声RMS,1e−8)仅为检查参考，不是显著性或真实性检验。

当前算法版本为 `simplex-nullspace-kkt-gaussian-v2`（旧版独立噪声）与 `simplex-nullspace-kkt-blank-joint-gls-v1`（空白联合协方差加权）。SHA256覆盖完整库/波长/端元/样本/批注快照、噪声参数或校准指纹、重复数、种子与算法版本。自然键排序使输入行序变化不改变结果；观测、波长、批注或参数改变会改变指纹。结果JSON及全部重复落在共享产物卷；数据库保存同一结果，CSV包含点估计、条件上下分位、RSS/RMSE、噪声模型/校准来源及指纹。

## 本地开发与结构

技术栈：Vue3.5 / TypeScript5.7 / Vite6.4 / Pinia3 / VueRouter4；Python3.11 / FastAPI0.115 / SQLAlchemy2 / NumPy2.2 / SciPy1.15 / PyMySQL1.1；MySQL8 / Redis7 / Nginx1.27。

```sh
# 先启动依赖，设置DATABASE_URL/REDIS_URL连接可用本地实例
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
# 另开终端（本地需要可写/artifacts；默认开发建议用Compose）
python -m src.worker
# 前端，Vite代理/api到localhost:8000
cd ../frontend
npm ci
npm run dev
```

`backend/src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}` 分离认证、来源、计算、建议与横切职责；`backend/scripts/seed_demo.py` 自然键seed；`backend/migrations/001_initial.sql` 是现有表的可选索引迁移，`002_blank_calibration.py` 为旧库补充空白校准表与运行校准外键，初次建表由SQLAlchemy metadata完成，不是独立全量DDL。`frontend/src/{api,stores,types,components,hooks,pages,router,utils,constants}` 是Vue应用，通用Notice/DataTable/StatusBadge与业务RunSummary/SpectralPlot跨页复用。

`.env` 参数有 COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET、SEED_DEMO；后端 DATABASE_URL、REDIS_URL 在Compose服务环境中定义。`.env`、构建目录、缓存与日志已忽略。角色枚举：`backend/src/constants/roles.py`、`frontend/src/constants/enums.ts`；运行状态：`backend/src/constants/status.py`、同一前端enums；审阅状态：`backend/src/schemas/note.py` Literal与前端ReviewStatus、model/default/service引用。共享枚举参与鉴权、worker状态与页面标签。

测试、真实截图、健康快照及已知差异在同批 `test-artifacts/gb-0019/TESTING.md`，源码不包含测试产物。当前实现是单worker本地研究系统，服务中断后的任务恢复/多worker去重、库上传管理、实测光谱校准、称量设备控制不在本项目范围。清理：`docker compose down -v --remove-orphans`（删除演示卷）。MIT License。
