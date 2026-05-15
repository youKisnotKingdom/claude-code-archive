from cc_history.services.markdown import render_markdown


def test_render_markdown_supports_common_blocks() -> None:
    html = render_markdown(
        "\n".join(
            [
                "## Heading",
                "",
                "- one",
                "- two",
                "",
                "```python",
                "print('hello')",
                "```",
                "",
                "[link](https://example.test)",
            ],
        ),
    )

    assert "<h2>Heading</h2>" in html
    assert "<li>one</li>" in html
    assert "language-python" in html
    assert 'href="https://example.test"' in html


def test_render_markdown_escapes_raw_html() -> None:
    html = render_markdown("<script>alert('x')</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
