# 兽药数据收集工作台

> Pet & Veterinary Drug Data Workbenches · 稳定云链接 · 每日自动更新

本仓库收纳了两个由 WorkBuddy 搭建的兽药数据工作台，统一部署到
**GitHub Pages**，提供长期稳定的访问链接，并实现每日自动抓取更新。

## 快速入口

| 工作台 | 覆盖范围 | 稳定链接 |
|---|---|---|
| 国际兽用生物制品监管追踪 | 美国 USDA/CVB、欧盟 EMA/CVMP 获批的猫犬兽用生物制品 | <https://qqkiky.github.io/vet-drug-workbenches/intl/> |
| 国内 / 进口兽药注册与审批 | 农业农村部公告：国产 / 进口新兽药注册、变更注册、临床审批 | <https://qqkiky.github.io/vet-drug-workbenches/cn/> |

两个站点都是 PWA（可安装的网页应用）：手机浏览器打开后选择
「添加到主屏幕」，即可当作独立 App 使用，数据更新后打开页面会自动刷新。

## 每日自动更新（混合架构）

| 工作台 | 更新方式 | 时间（北京时间） | 原因 |
|---|---|---|---|
| 国际 | GitHub Actions 云端定时抓取 | 每天 20:00 | 云端可直接访问 USDA/EMA 官方站点，无需电脑开机 |
| 国内 | 本机定时任务抓取 + 自动推送 | 每天 20:00 | 国内兽药数据库从云端不可达，保留本机抓取，完成后推送到仓库 |

两条链路最终都汇入本仓库：每次推送后，GitHub Pages 会自动重新发布，
所以云链接始终展示最新数据。

## 目录结构

```
├── README.md                    # 本文件（总览）
├── docs/
│   ├── 部署说明.md              # 操作手册：构建 / 更新 / 故障排查
│   ├── 变更日志.md              # 每日更新记录（自动追加）
│   └── 国际生物制品工作台-技术说明.md  # 海外工作台原技术文档
├── .github/workflows/
│   ├── pages.yml                # 推送后自动发布 GitHub Pages
│   └── daily-intl.yml           # 海外工作台每日 20:00 云端同步
├── publish_site.py              # 组装统一站点（intl/ + cn/ + 入口页）
├── git_sync.py                  # 本地更新后自动提交并推送
├── app.py / db.py / ingest.py / regulatory.py / build_static.py / daily_sync.py
│                                # 海外工作台源码（Flask + SQLite + 抓取）
├── static/                      # 海外工作台前端源码
├── dist/                        # 海外工作台构建产物（发布用）
├── data/                        # 海外工作台数据库与抓取缓存
└── workbench/                   # 国内/进口工作台
    ├── drugs.db                 # 注册审批主数据库
    ├── build_web.py             # 从数据库生成 web/ 静态站点
    ├── build_workbench.py       # 抓取农业农村部公告 + 生成工作簿
    ├── ingest_vdts_clinical.py  # 导入临床审批数据
    ├── fill_all_indications.py  # 补全适应症
    ├── web/                     # 国内工作台构建产物（发布用）
    └── *.xlsx                   # 可下载的 Excel 工作台报表
```

## 使用与维护

- 日常操作、手动更新、故障排查：见 [docs/部署说明.md](docs/部署说明.md)
- 数据更新记录：见 [docs/变更日志.md](docs/变更日志.md)
- 海外工作台详细技术说明：见 [docs/国际生物制品工作台-技术说明.md](docs/国际生物制品工作台-技术说明.md)
- 国内工作台详细说明：见 [workbench/README.md](workbench/README.md)

## 数据来源与声明

- 国内数据：农业农村部公告（[中国兽药信息网](http://www.ivdc.org.cn)）
- 海外数据：美国 [USDA/APHIS CVB](https://www.aphis.usda.gov) 产品目录、
  欧盟 [EMA/CVMP](https://www.ema.europa.eu) 兽药数据库
- 本站仅做整理与检索，不构成任何用药或注册建议；数据以官方原文为准。

## 隐私与安全

仓库为**公开**性质，本地会话记录、依赖环境、抓取缓存、邮件配置等均通过
`.gitignore` 排除，不会上传。
