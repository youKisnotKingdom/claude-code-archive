from functools import lru_cache

from markdown_it import MarkdownIt


@lru_cache(maxsize=1)
def _markdown_renderer() -> MarkdownIt:
    return MarkdownIt("default", {"html": False, "linkify": False})


def render_markdown(text: str) -> str:
    return _markdown_renderer().render(text)
