# 兽药注册与审批数据查询工作台（PC + 移动端同源同步）

宠物药 / 兽药注册审批、临床审批数据查询工作台。**PC 端与移动端共用同一份网页产物**，移动端可“添加到主屏幕”作为独立 App 安装使用，两端内容、功能、数据完全同源一致，任一端（后台重建并部署）更新后，已打开的页面会自动同步刷新。

工程根目录：`D:\WorkBuddyProjects\宠物药数据收集\workbench\`

---

## 1. 目录结构

```
workbench/
├── drugs.db                # SQLite 主数据库（drugs 表=注册审批2209条；clinical_approval 表=临床审批939条；update_log=更新动态）
├── build_web.py            # ★ 核心：从 drugs.db 生成 web/index.html 及全部 PWA 资源
├── ingest_vdts_clinical.py # 从国家兽药基础数据库全量导入临床审批（截止 2026-07-09，934条）
├── fill_all_indications.py # 为全部产品补全适应症（覆盖 100%）
├── indication_extra.json / indication_online.json  # 成分→适应症映射
├── vdts_lcsysp_20260709.json  # 临床审批原始抓取数据
├── verify_pwa.py           # 本地移动端 PWA 自动化验证（Playwright + Edge 移动视口）
├── web/                    # ★ 部署产物（PC 与移动端同源）
│   ├── index.html          # 自包含静态单页（数据内嵌 JSON，纯前端无后端）
│   ├── manifest.json       # PWA 清单（名称/图标/standalone 显示）
│   ├── sw.js               # Service Worker（导航网络优先 + 离线缓存 + 自动更新）
│   ├── version.json        # 构建版本号（自动同步检测依据）
│   ├── icon-192.png        # PWA 图标
│   └── icon-512.png        # PWA 图标
└── *.xlsx                 # 导出的各类工作台报表
```

> 说明：上一级目录 `D:\WorkBuddyProjects\宠物药数据收集\` 另含一个早期独立项目（app.py / db.py 等 Flask 双语 SPA），与本工作台无关，未纳入本工程。

---

## 2. PC 端 与 移动端 同源同步架构

```
                ┌─────────────────────────────────────────┐
                │        drugs.db（唯一数据源）              │
                └───────────────────┬─────────────────────┘
                                    │  build_web.py 每次重建
                                    ▼
                ┌─────────────────────────────────────────┐
                │   web/ 静态产物（同一份 index.html）       │
                │   index.html + manifest.json + sw.js      │
                │   + version.json + icons                  │
                └───────────────────┬─────────────────────┘
                                    │  部署到同一 URL
                                    ▼
        PC 浏览器 ───────────┐              ┌─────────── 手机浏览器 / 主屏 App
        （同一地址）          │  同源同步     │  （同一地址，manifest 安装）
                              ▼              ▼
                  两端加载完全相同的页面与内嵌数据
```

- **内容/功能完全一致**：PC 与移动端加载的是同一个 `web/index.html`，没有任何分支或复本，因此查询、筛选、分页、CSV 导出、临床审批动态、更新动态等功能两端完全一致。
- **自动同步（实时一致）**：当后台重新跑 `build_web.py` 并部署后，`version.json` 的 `build` 版本号变化。已打开的页面会：
  1. 每 60 秒、且每次从后台切回前台时，拉取 `version.json` 比对；若版本不同则自动刷新页面，获取最新数据；
  2. 同时 Service Worker 检测到 `sw.js` 更新后自动接管并刷新。
  因此任一端（实际是同一后端数据源）更新后，两端都会自动同步到最新内容。

---

## 3. 构建与部署

```bash
# 1) 重建网页与 PWA 资源（依赖 PIL 生成图标，已随环境就绪）
python build_web.py
#    输出：web/index.html(2209 注册 / 939 临床) + manifest.json + sw.js + version.json + icons

# 2) 本地移动端验证（可选，需 Playwright + Edge）
python verify_pwa.py
#    检查：manifest 合法、Service Worker 注册成功、version.json 可访问、数据渲染、无控制台报错

# 3) 部署到 CloudStudio（静态站点）
#    通过 workbuddy_cloudstudio_deploy 部署 workbench/web 目录
#    访问地址：https://0139e7901ac6450c8824425ec9ce15a3.bj7.agentos-app.net
```

---

## 4. 手机安装为桌面 App（iOS / Android）

1. 用手机浏览器打开部署地址。
2. **Android（Chrome）**：右上角菜单 →「添加到主屏幕」→ 命名后确认。
3. **iOS（Safari）**：底部分享按钮 →「添加到主屏幕」→ 添加。
4. 主屏出现图标，点击即以独立全屏 App 打开，体验与 PC 完全一致；后台数据更新后打开/切回即自动刷新。

---

## 5. 数据管线（每日自动化）

- `ingest_vdts_clinical.py`：全量导入国家兽药基础数据库临床审批数据。
- `fill_all_indications.py`：为全部产品补全适应症。
- 自动化任务 `automation-1785242856431`（兽药注册工作台每日更新）已纳入上述两步，保持两端数据持续更新。

---

## 6. 关键工程经验

- 国家兽药基础数据库真实列表接口为**双 `/api`** 路径：`http://vdts.ivdc.org.cn:8099/api/api/cx/h5/lcsysp/list`（POST `{"page":N,"rows":100,"conditionItems":[]}`）。
- 本工作台为**纯静态单页**（数据内嵌），无需后端即可运行；PWA 的 Service Worker 仅用于「可安装 + 离线缓存 + 自动更新」，不改变数据同源逻辑。
- 修改 `build_web.py` 时注意：模板中 `<title>` 等含中文行**不要用含中文的精确字符串做替换**（易因 Unicode 规范化不匹配而失败），应改用 ASCII 锚点 + 正则（如 `re.sub(r'<title>.*?</title>', ...)`）。
