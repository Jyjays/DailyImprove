from app.plugins.base import SourcePlugin
from app.plugins.sources.api_source import ApiSourcePlugin
from app.plugins.sources.rss_source import RssSourcePlugin
from app.plugins.sources.search_source import SearchSourcePlugin
from app.plugins.sources.web_source import WebSourcePlugin

SOURCE_PLUGINS: dict[str, SourcePlugin] = {
    cls.name: cls()
    for cls in [RssSourcePlugin, ApiSourcePlugin, WebSourcePlugin, SearchSourcePlugin]
}


def get_source_plugin(name: str) -> SourcePlugin:
    if name not in SOURCE_PLUGINS:
        raise KeyError(f"未知来源类型: {name}，已注册: {list(SOURCE_PLUGINS)}")
    return SOURCE_PLUGINS[name]
