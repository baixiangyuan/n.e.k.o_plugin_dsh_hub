"""
DSH 插件中心 v0.1 (DSH Plugin Hub)

在 N.E.K.O 里浏览、搜索并使用 DeepSeek Harness（DSH）插件市场的 4000+ 插件。
内置网页面板（原生 context/action + 自定义 static 网页），猫娘也能在聊天里帮你推荐。

重要说明:
  DSH 插件是运行在 DeepSeek Harness（Node/Cordis）运行时里的 TypeScript 模块，
  无法被 N.E.K.O 直接加载执行。本插件做的是「发现 + 桥接」：
    - 浏览/搜索 DSH 市场目录
    - 查看某插件的简介、安装命令、GitHub 仓库
    - 给出在 DSH 里安装它的命令（dsh plugin --profile web add github:<owner>/<repo>）
  真正的执行发生在用户的 DSH 实例中。

入口（面板动作 / LLM 工具）:
  - search        : 按关键词搜索插件（面板 + 聊天）
  - open_detail    : 查看某插件详情与安装命令（面板）
  - close_detail   : 关闭详情（面板）
  - dsh_recommend  : 猫娘在聊天里按主题推荐插件（LLM 工具）
"""

from __future__ import annotations

from typing import Any

from plugin.sdk.plugin import (
    Err,
    NekoPluginBase,
    Ok,
    SdkError,
    lifecycle,
    llm_tool,
    neko_plugin,
    plugin_entry,
)
from plugin.sdk.plugin.ui import action as ui_action
from plugin.sdk.plugin.ui import context as ui_context

from .dsh_core import DshCatalog

_PLUGIN_ID = "dsh_hub"
_DEFAULTS = {
    "catalog_url": "https://dsh-plugin.org/zh/plugins",
    "detail_base_url": "https://dsh-plugin.org/zh/plugins",
    "catalog_cache_ttl": 3600,
    "page_size": 24,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


def _read_cfg(ctx: Any, key: str, default: Any) -> Any:
    """安全读取 plugin.toml 的 [dsh_hub] 配置段字段。"""
    try:
        section = getattr(ctx.config, "dsh_hub", None)
        if section is not None:
            val = getattr(section, key, None)
            if val is not None:
                return val
    except Exception:
        pass
    return default


@neko_plugin
class DshHubPlugin(NekoPluginBase):
    """DSH 插件中心 - N.E.K.O 插件入口"""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self.catalog = self._build_catalog()
        # 面板状态（context 返回给前端）
        self._state: dict[str, Any] = {
            "query": "",
            "total": 0,
            "page": 1,
            "page_size": _DEFAULTS["page_size"],
            "page_count": 1,
            "results": [],
            "detail": None,
            "categories": [],
            "loaded": False,
            "error": "",
        }

    def _build_catalog(self) -> DshCatalog:
        return DshCatalog(
            catalog_url=str(_read_cfg(self.ctx, "catalog_url", _DEFAULTS["catalog_url"])),
            detail_base_url=str(_read_cfg(self.ctx, "detail_base_url", _DEFAULTS["detail_base_url"])),
            cache_ttl=int(_read_cfg(self.ctx, "catalog_cache_ttl", _DEFAULTS["catalog_cache_ttl"])),
            user_agent=str(_read_cfg(self.ctx, "user_agent", _DEFAULTS["user_agent"])),
            timeout=25.0,
        )

    # ── 生命周期 ───────────────────────────────────────────────
    @lifecycle
    async def on_startup(self) -> None:
        self.logger.info("[dsh_hub] 启动：DSH 插件中心已就绪")
        # 预热：抓取一次目录并缓存，面板打开即快
        try:
            self.catalog.get_catalog(force=False)
            self._state["loaded"] = True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("[dsh_hub] 预热目录失败（将在首次搜索时重试）: %s", exc)

    @lifecycle
    async def on_shutdown(self) -> None:
        self.logger.info("[dsh_hub] 关闭：DSH 插件中心")

    # ── 面板状态 ───────────────────────────────────────────────
    @ui_context(id="main", title="DSH 插件中心")
    async def get_ui_context(self) -> dict[str, Any]:
        # 首次打开面板时若还没数据，自动加载第一页
        if not self._state.get("loaded") and not self._state.get("results"):
            try:
                result = self.catalog.search(page=1, page_size=self._state["page_size"])
                self._state.update(
                    {
                        "query": result["query"],
                        "total": result["total"],
                        "page": result["page"],
                        "page_size": result["page_size"],
                        "page_count": result["page_count"],
                        "results": result["results"],
                        "categories": self.catalog.categories()[:50],
                        "loaded": True,
                        "error": "",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                self._state["error"] = f"加载目录失败：{exc}"
        return dict(self._state)

    # ── 动作：搜索 ─────────────────────────────────────────────
    @ui_action(
        id="search",
        label="搜索插件",
        icon="🔍",
        group="browse",
        order=10,
        refresh_context=True,
    )
    @plugin_entry(
        id="search",
        name="搜索 DSH 插件",
        description="按关键词（插件名/作者/仓库名）搜索 DSH 插件市场，返回分页结果。",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，例如 modlens、vision、图片、dsh-market",
                },
                "page": {
                    "type": "integer",
                    "description": "页码，从 1 开始",
                    "default": 1,
                },
            },
        },
    )
    async def search_entry(self, **kwargs):
        query = str(kwargs.get("query") or "")
        page = int(kwargs.get("page") or 1)
        try:
            result = self.catalog.search(query=query, page=page, page_size=self._state["page_size"])
            self._state.update(
                {
                    "query": result["query"],
                    "total": result["total"],
                    "page": result["page"],
                    "page_size": result["page_size"],
                    "page_count": result["page_count"],
                    "results": result["results"],
                    "detail": None,
                    "error": "",
                }
            )
            return Ok(
                {
                    "ok": True,
                    "total": result["total"],
                    "returned": len(result["results"]),
                    "page": result["page"],
                    "page_count": result["page_count"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._state["error"] = f"搜索失败：{exc}"
            return Err(SdkError(f"搜索失败：{exc}"))

    # ── 动作：查看详情 ─────────────────────────────────────────
    @ui_action(
        id="open_detail",
        label="查看详情",
        icon="📦",
        group="browse",
        order=20,
        refresh_context=True,
    )
    @plugin_entry(
        id="open_detail",
        name="查看 DSH 插件详情",
        description="获取某个 DSH 插件的详细信息：描述、分类、安装命令、GitHub 仓库与 Star 数。",
        input_schema={
            "type": "object",
            "properties": {
                "author": {"type": "string", "description": "插件作者/组织，例如 liustack"},
                "name": {"type": "string", "description": "插件仓库名/slug，例如 modlens"},
            },
        },
    )
    async def open_detail_entry(self, **kwargs):
        author = str(kwargs.get("author") or "").strip()
        name = str(kwargs.get("name") or "").strip()
        if not author or not name:
            return Err(SdkError("需要提供 author 与 name"))
        try:
            detail = self.catalog.get_detail(author, name)
            self._state["detail"] = detail.to_dict()
            return Ok(detail.to_dict())
        except Exception as exc:  # noqa: BLE001
            self._state["error"] = f"获取详情失败：{exc}"
            return Err(SdkError(f"获取详情失败：{exc}"))

    # ── 动作：关闭详情 ─────────────────────────────────────────
    @ui_action(
        id="close_detail",
        label="返回列表",
        icon="↩️",
        group="browse",
        order=30,
        refresh_context=True,
    )
    @plugin_entry(
        id="close_detail",
        name="关闭插件详情",
        description="关闭当前插件详情，回到搜索列表。",
    )
    async def close_detail_entry(self, **kwargs):
        self._state["detail"] = None
        return Ok({"ok": True})

    # ── LLM 工具：让猫娘在聊天里推荐 ──────────────────────────
    @llm_tool
    @plugin_entry(
        id="dsh_recommend",
        name="推荐 DSH 插件",
        description="根据主题或需求，从 DSH 插件市场搜索并推荐合适的 DeepSeek Harness 插件，返回名称、简介与安装命令。",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "需求主题，例如：图片识别、记忆、网页搜索、代码执行、语音",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回几条推荐",
                    "default": 5,
                },
            },
        },
    )
    async def dsh_recommend(self, topic: str = "", limit: int = 5, **_):
        topic = (topic or "").strip()
        limit = max(1, min(20, int(limit or 5)))
        if not topic:
            return Err(SdkError("请告诉我你想找什么类型的插件～"))
        try:
            result = self.catalog.search(query=topic, page=1, page_size=limit)
            items = result["results"][:limit]
            if not items:
                return Ok({"found": False, "message": f"没有找到和「{topic}」相关的 DSH 插件，换个关键词试试？"})
            lines = [f"在 DSH 插件市场找到 {result['total']} 个和「{topic}」相关的插件，给你挑 {len(items)} 个："]
            for idx, it in enumerate(items, 1):
                lines.append(f"{idx}. {it['name']}（by {it['author']}）\n   {it['url']}")
            lines.append("在 N.E.K.O 的 DSH 插件中心面板里点开即可复制安装命令，回到你的 DSH 实例执行即可使用。")
            return Ok({"found": True, "count": len(items), "message": "\n".join(lines)})
        except Exception as exc:  # noqa: BLE001
            return Err(SdkError(f"推荐失败：{exc}"))
