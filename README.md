# 兽药数据收集工作台

> Pet & Veterinary Drug Data Workbenches · 稳定云链接 · 自动增量更新

本仓库收纳两个兽药数据工作台，统一通过 **GitHub Pages** 发布。数据同步、
去重、审计记录和网页重建由 GitHub Actions 在云端完成，不依赖本机开机。

## 快速入口

| 工作台 | 覆盖范围 | 稳定链接 |
|---|---|---|
| 国际兽用生物制品监管追踪 | 美国 USDA/CVB、欧盟 EMA/CVMP 获批的猫犬兽用生物制品 | <https://qqkiky.github.io/vet-drug-workbenches/intl/> |
| 国内 / 进口兽药注册与审批 | 农业农村部公告：国产 / 进口新兽药注册、变更注册、临床审批 | <https://qqkiky.github.io/vet-drug-workbenches/cn/> |

两个站点都是 PWA（可安装的网页应用）。数据发布后，已打开页面会通过
版本检测与 Service Worker 自动刷新。

## 自动更新

GitHub Actions 工作流 `.github/workflows/daily-intl.yml` 在北京时间
**每周三、每周五 22:00** 自动运行，也支持在 Actions 页面手动触发。

一次运行会：

1. 同步国际数据：USDA/CVB 产品目录与 EMA/CVMP 数据库；
2. 同步国内数据：农业农村部公告与国家兽药基础数据库临床审批；
3. 按自然键增量写入并去重，不以空抓取覆盖已有数据；
4. 重建数据库、Excel、静态网页和 PWA 资源；
5. 更新 `data/sync_state.json`、`data/cn_sync_state.json` 与
   `docs/变更日志.md`；
6. 自动提交到 `main`，随后由 `pages.yml` 发布 GitHub Pages。

若某个来源临时不可用，其余来源仍可更新并记录为 `partial`；同一工作台的
所有官方来源都失败时，不发布旧数据冒充成功。

## 目录结构

```
├── README.md
├── docs/
│   ├── 部署说明.md
│   ├── 变更日志.md
│   └── 国际生物制品工作台-技术说明.md
├── .github/workflows/
│   ├── pages.yml
│   ├── daily-intl.yml
│   └── backfill-intl.yml
├── daily_sync.py                  # 国际增量同步
├── tools/cn_cloud_sync.py         # 国内云端同步与审计编排
├── publish_site.py                # 组装 intl/、cn/ 与入口页
├── data/                          # 国际数据库及同步状态
├── dist/                          # 国际工作台发布产物
└── workbench/
    ├── drugs.db                   # 国内注册与临床审批主数据库
    ├── build_workbench.py         # 农业农村部公告增量抓取
    ├── ingest_vdts_clinical.py    # 临床审批实时抓取
    ├── build_web.py               # 生成国内静态站点
    ├── web/                       # 国内发布产物
    └── *.xlsx                     # 可下载报表
```

## 使用与维护

- 日常操作与故障排查：[docs/部署说明.md](docs/部署说明.md)
- 自动更新记录：[docs/变更日志.md](docs/变更日志.md)
- 国际工作台技术说明：[docs/国际生物制品工作台-技术说明.md](docs/国际生物制品工作台-技术说明.md)
- 国内工作台说明：[workbench/README.md](workbench/README.md)

## 数据来源与声明

- 国内数据：农业农村部公告（[中国兽药信息网](http://www.ivdc.org.cn)）及
  国家兽药基础数据库；
- 海外数据：美国 [USDA/APHIS CVB](https://www.aphis.usda.gov) 产品目录及
  欧盟 [EMA/CVMP](https://www.ema.europa.eu) 兽药数据库；
- 本站仅做整理与检索，不构成任何用药、诊断或注册建议；以官方原文为准。

## 隐私与安全

仓库为公开仓库。本地会话、虚拟环境、邮件配置、临时抓取缓存和运行日志均由
`.gitignore` 排除，不应提交任何凭据或个人信息。
