"""DSH 插件中心 - 核心抓取与解析（纯标准库，无第三方依赖）。

职责:
  - 抓取 dsh-plugin.org 中文目录页，正则提取全部插件清单（name + url + slug）
  - 按关键词/作者搜索并分页
  - 抓取单个插件详情页，解析：描述、安装命令、GitHub 仓库、分类、Star 数

注意: DSH 插件本质是 DeepSeek Harness 的 TypeScript/Cordis 模块，运行在 DSH 的
Node 运行时里，无法被 N.E.K.O 直接加载执行。本模块只负责把市场里的插件「找出来、
看清楚、给出在 DSH 里安装/使用的命令」，即在 N.E.K.O 一侧做桥接与发现。
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

_LIST_ITEM_RE = re.compile(
    r'"@type":"ListItem","position":\d+,"name":"(?P<name>[^"]+)","url":"(?P<url>[^"]+)"'
)
_INSTALL_RE = re.compile(r"dsh\s+plugin[^\n\"'<]{0,160}?add\s+github:([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)")
_GH_REF_RE = re.compile(r"github:([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)")
_GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)")
_STAR_RE = re.compile(r"([\d,]+)\s*Star")
_CATEGORY_RE = re.compile(r"分类\s*</[^>]+>\s*<[^>]+>([^<]+)</", re.IGNORECASE)
_META_DESC_RE = re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', re.IGNORECASE)
_OG_DESC_RE = re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.IGNORECASE)


@dataclass
class PluginSummary:
    name: str
    author: str
    slug: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "author": self.author, "slug": self.slug, "url": self.url}


@dataclass
class PluginDetail:
    name: str
    author: str
    slug: str
    url: str
    description: str = ""
    category: str = ""
    github: str = ""
    install_command: str = ""
    stars: str = ""
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "author": self.author,
            "slug": self.slug,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "github": self.github,
            "install_command": self.install_command,
            "stars": self.stars,
        }


class DshCatalog:
    """DSH 插件市场目录抓取器（带内存缓存）。"""

    def __init__(
        self,
        catalog_url: str = "https://dsh-plugin.org/zh/plugins",
        detail_base_url: str = "https://dsh-plugin.org/zh/plugins",
        cache_ttl: int = 3600,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        timeout: float = 25.0,
    ) -> None:
        self.catalog_url = catalog_url
        self.detail_base_url = detail_base_url.rstrip("/")
        self.cache_ttl = cache_ttl
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: list[PluginSummary] = []
        self._cache_at: float = 0.0

    # ── 底层 HTTP ───────────────────────────────────────────────
    def _fetch(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Language": "zh-CN,zh;q=0.9"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")

    # ── 目录 ───────────────────────────────────────────────────
    def get_catalog(self, force: bool = False) -> list[PluginSummary]:
        now = time.time()
        if self._cache and not force and (now - self._cache_at) < self.cache_ttl:
            return self._cache
        raw = self._fetch(self.catalog_url)
        items = self._parse_catalog(raw)
        self._cache = items
        self._cache_at = now
        return items

    @staticmethod
    def _parse_catalog(raw: str) -> list[PluginSummary]:
        out: list[PluginSummary] = []
        seen: set[str] = set()
        for match in _LIST_ITEM_RE.finditer(raw):
            name = html.unescape(match.group("name"))
            url = html.unescape(match.group("url"))
            # url 形如 https://dsh-plugin.org/zh/plugins/<author>/<name>
            m = re.search(r"/zh/plugins/([^/]+)/([^/?#]+)", url)
            if not m:
                continue
            author = html.unescape(m.group(1))
            slug = html.unescape(m.group(2))
            key = f"{author}/{slug}"
            if key in seen:
                continue
            seen.add(key)
            out.append(PluginSummary(name=name, author=author, slug=slug, url=url))
        return out

    # ── 搜索 + 分页 ────────────────────────────────────────────
    def search(
        self,
        query: str = "",
        author: str = "",
        page: int = 1,
        page_size: int = 24,
    ) -> dict[str, Any]:
        catalog = self.get_catalog()
        q = (query or "").strip().lower()
        a = (author or "").strip().lower()
        if q:
            filtered = [
                item
                for item in catalog
                if q in item.name.lower() or q in item.slug.lower() or q in item.author.lower()
            ]
        else:
            filtered = list(catalog)
        if a:
            filtered = [item for item in filtered if a in item.author.lower()]
        total = len(filtered)
        page = max(1, int(page))
        start = (page - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]
        return {
            "query": query or "",
            "author": author or "",
            "total": total,
            "page": page,
            "page_size": page_size,
            "page_count": max(1, (total + page_size - 1) // page_size),
            "results": [item.to_dict() for item in page_items],
        }

    def categories(self) -> list[str]:
        """返回去重后的作者列表（按插件数排序），作为「分类/来源」筛选维度。"""
        catalog = self.get_catalog()
        counts: dict[str, int] = {}
        for item in catalog:
            counts[item.author] = counts.get(item.author, 0) + 1
        return [author for author, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]

    # ── 详情 ───────────────────────────────────────────────────
    def get_detail(self, author: str, slug: str) -> PluginDetail:
        url = f"{self.detail_base_url}/{author}/{slug}"
        raw = self._fetch(url)
        return self._parse_detail(raw, author, slug, url)

    @staticmethod
    def _parse_detail(raw: str, author: str, slug: str, url: str) -> PluginDetail:
        # 清理脚本/样式，取纯文本用于兜底描述
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        # 名称：优先卡片标题，否则用 slug
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', raw)
        name = html.unescape(name_match.group(1).strip()) if name_match else slug

        # 安装命令
        install_cmd = ""
        m = _INSTALL_RE.search(raw)
        if m:
            install_cmd = f"dsh plugin --profile web add github:{m.group(1)}"
        else:
            g = _GITHUB_RE.search(raw)
            if g:
                install_cmd = f"dsh plugin --profile web add github:{g.group(1)}"

        # GitHub 仓库：优先取 `github:owner/repo`（即插件真实仓库），兜底取页面里第一个 github.com 链接
        github = ""
        ghr = _GH_REF_RE.search(raw)
        if ghr:
            github = ghr.group(1)
        else:
            gm = _GITHUB_RE.search(raw)
            if gm:
                github = gm.group(1)

        # 描述
        desc = ""
        dm = _META_DESC_RE.search(raw) or _OG_DESC_RE.search(raw)
        if dm:
            desc = html.unescape(dm.group(1)).strip()
        if not desc:
            # 取正文前 200 字
            desc = text[:200].strip()

        # 分类
        category = ""
        cm = _CATEGORY_RE.search(raw)
        if cm:
            category = html.unescape(cm.group(1)).strip()

        # Star 数
        stars = ""
        sm = _STAR_RE.search(text)
        if sm:
            stars = sm.group(1)

        return PluginDetail(
            name=name,
            author=author,
            slug=slug,
            url=url,
            description=desc,
            category=category,
            github=github,
            install_command=install_cmd,
            stars=stars,
            raw_text=text[:1000],
        )

    # ── 供单测使用的离线解析（不联网）─────────────────────────
    @staticmethod
    def parse_catalog_html(raw: str) -> list[PluginSummary]:
        return DshCatalog._parse_catalog(raw)

    @staticmethod
    def parse_detail_html(raw: str, author: str, slug: str, url: str = "") -> PluginDetail:
        return DshCatalog._parse_detail(raw, author, slug, url or f"https://dsh-plugin.org/zh/plugins/{author}/{slug}")
