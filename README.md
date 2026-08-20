# 🐱 DSH 插件中心 (dsh_hub)

在 **N.E.K.O** 里浏览、搜索并使用 [DeepSeek Harness（DSH）插件市场](https://dsh-plugin.org/zh/plugins) 的 4000+ 插件。内置网页面板，猫娘也能在聊天里帮你推荐。

> ⚠️ **关于「在 N.E.K.O 里用 DSH 插件」**
> DSH 插件是运行在 DeepSeek Harness（Node/Cordis）运行时里的 TypeScript 模块，**无法被 N.E.K.O 直接加载执行**。本插件做的是「发现 + 桥接」：
> - 浏览 / 搜索 DSH 市场目录
> - 查看某插件的简介、分类、安装命令、GitHub 仓库、Star 数
> - 给出在 DSH 里安装它的命令：`dsh plugin --profile web add github:<owner>/<repo>`
>
> 真正的执行发生在你自己的 DSH 实例中。本中心负责把对的插件找出来、把命令准备好。

## ✨ 功能

| 能力 | 入口 | 说明 |
|------|------|------|
| 🔍 搜索插件 | 面板「搜索插件」/ 聊天 | 按插件名 / 作者 / 仓库名搜索，分页展示 |
| 📦 查看详情 | 面板点击卡片 | 描述、分类、安装命令（可复制）、GitHub 链接、Star 数 |
| 💬 猫娘推荐 | 聊天 `dsh_recommend` | 按主题需求推荐合适的 DSH 插件 |

## 🖥️ Web UI

插件声明了 `[plugin.ui.panel]`（static 模式），在 N.E.K.O 插件面板里打开即为一个完整的网页：
- 顶部搜索框 + 实时结果网格
- 点击卡片查看详情，一键复制安装命令、跳转 GitHub
- 调用同源 REST（`/plugin/dsh_hub/hosted-ui/context` 与 `/hosted-ui/action/<id>`）与后端通信

## 📁 结构

```
dsh_hub/
├── plugin.toml          # 插件元信息 + UI 面板声明
├── __init__.py          # DshHubPlugin 入口（context/action/llm_tool）
├── dsh_core.py          # 抓取与解析（纯标准库，无第三方依赖）
├── static/index.html    # 网页面板 UI
├── i18n/                # 中/英文案
├── tests/test_smoke.py  # 冒烟测试
└── .github/workflows/   # verify / release 工作流
```

## 🔧 本地开发

```bash
python -m unittest tests.test_smoke -v
```

## 📦 发布到 N.E.K.O 市场

打 `vX.Y.Z` 标签（需与 `plugin.toml` 的 `version` 一致）并推送即可触发发布工作流：

```bash
git tag v0.1.0 && git push origin v0.1.0
```
