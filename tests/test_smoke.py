"""DSH 插件中心 - 冒烟测试（纯标准库，不依赖 SDK）。

覆盖:
  - 仓库根结构 / plugin.toml entry 格式
  - dsh_core 的目录解析与详情解析（用内嵌样例 HTML，无需联网）
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ID = "dsh_hub"

# ── 样例 HTML（内嵌，避免联网）─────────────────────────────
SAMPLE_CATALOG = """
<html><body>
<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
{"@type":"ListItem","position":1,"name":"modlens","url":"https://dsh-plugin.org/zh/plugins/liustack/modlens"},
{"@type":"ListItem","position":2,"name":"dsh-tui","url":"https://dsh-plugin.org/zh/plugins/ccch1mneyyy/dsh-tui"}
]}</script>
inEntity":{"@type":"ItemList","itemListElement":[
{"@type":"ListItem","position":1,"name":"modlens","url":"https://dsh-plugin.org/zh/plugins/liustack/modlens"},
{"@type":"ListItem","position":2,"name":"dsh-better-sidebar","url":"https://dsh-plugin.org/zh/plugins/omdsh-dev/dsh-better-sidebar"},
{"@type":"ListItem","position":3,"name":"dsh-tui","url":"https://dsh-plugin.org/zh/plugins/ccch1mneyyy/dsh-tui"}
]}
</body></html>
"""

SAMPLE_DETAIL = """
<html><head>
<meta name="description" content="ModLens 为 DeepSeek Harness 的纯文本模型外挂视觉能力。" />
</head><body>
<h1>modlens</h1>
分类</td><td><a>工具与能力</a></td>
<p>3,341 Star 90 Fork</p>
<p>安装 ModLens 只需一条命令：dsh plugin --profile web add github:liustack/modlens 即可。</p>
<a href="https://github.com/liustack/modlens">GitHub</a>
</body></html>
"""


def load_core():
    """加载 dsh_core.py 供测试使用（注册进 sys.modules 以兼容 dataclasses）。"""
    import sys

    core_path = os.path.join(ROOT, "dsh_core.py")
    spec = importlib.util.spec_from_file_location("dsh_core_test", core_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dsh_core_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestStructure(unittest.TestCase):
    def test_plugin_toml_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "plugin.toml")))

    def test_init_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "__init__.py")))

    def test_static_panel_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "static", "index.html")))

    def test_entry_format(self):
        with open(os.path.join(ROOT, "plugin.toml"), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r'^entry\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(m, "plugin.toml 缺少 entry")
        entry = m.group(1)
        self.assertTrue(
            entry.startswith(f"plugins.{PLUGIN_ID}:"),
            f"entry 应以 plugins.{PLUGIN_ID}: 开头，实际为 {entry}",
        )
        self.assertIn("DshHubPlugin", entry)

    def test_ui_panel_declared(self):
        with open(os.path.join(ROOT, "plugin.toml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('[plugin.ui.panel]', text)
        self.assertIn('entry = "static/index.html"', text)
        self.assertIn('mode = "static"', text)


class TestCatalogParsing(unittest.TestCase):
    def setUp(self):
        self.core = load_core()

    def test_parse_catalog_html(self):
        items = self.core.DshCatalog.parse_catalog_html(SAMPLE_CATALOG)
        # 仅 SAMPLE_CATALOG 含 5 条（2 条 ld+json + 3 条 inEntity，去重后 3 条）
        names = {it.name for it in items}
        self.assertIn("modlens", names)
        self.assertIn("dsh-tui", names)
        self.assertIn("dsh-better-sidebar", names)
        for it in items:
            self.assertTrue(it.author)
            self.assertTrue(it.slug)
            self.assertTrue(it.url.startswith("https://dsh-plugin.org/zh/plugins/"))

    def test_search_filter(self):
        cat = self.core.DshCatalog()
        cat._cache = self.core.DshCatalog.parse_catalog_html(SAMPLE_CATALOG)
        cat._cache_at = __import__("time").time()
        res = cat.search(query="dsh-tui", page=1, page_size=10)
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["results"][0]["slug"], "dsh-tui")

    def test_parse_detail_html(self):
        d = self.core.DshCatalog.parse_detail_html(SAMPLE_DETAIL, "liustack", "modlens")
        self.assertEqual(d.name, "modlens")
        self.assertIn("github:liustack/modlens", d.install_command)
        self.assertEqual(d.github, "liustack/modlens")
        self.assertIn("视觉", d.description)
        self.assertEqual(d.stars, "3,341")


if __name__ == "__main__":
    unittest.main(verbosity=2)
