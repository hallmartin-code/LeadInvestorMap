"""The favicon and the public directory it lives in."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.web import theme

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_the_public_directory_holds_the_icon_set():
    for name in ("favicon.png", "favicon.ico", "apple-touch-icon.png"):
        path = STATIC / name
        assert path.exists(), f"missing {name}"
        assert path.stat().st_size > 0


def test_the_png_icon_is_square_and_large_enough():
    with Image.open(STATIC / "favicon.png") as image:
        assert image.width == image.height, "a favicon must be square"
        assert image.width >= 180, "too small to downscale cleanly for retina tabs"
        assert image.mode in {"RGBA", "RGB", "P"}


def test_the_ico_carries_the_small_sizes_browsers_ask_for():
    with Image.open(STATIC / "favicon.ico") as image:
        sizes = {size for size in image.info.get("sizes", set())}
    assert (16, 16) in sizes and (32, 32) in sizes


def test_the_apple_touch_icon_is_opaque():
    """iOS composites transparency onto black, which would lose the mark's white centre."""
    with Image.open(STATIC / "apple-touch-icon.png") as image:
        assert image.size == (180, 180)
        assert image.mode == "RGB" or "A" not in image.getbands()


def test_the_icon_carries_the_brand_colours():
    """The mark is coral, amber and teal; a placeholder or wrong file would not be."""
    with Image.open(STATIC / "favicon.png") as image:
        pixels = image.convert("RGB").resize((64, 64)).getdata()

    def near(pixel, target, tolerance=60):
        return all(abs(a - b) <= tolerance for a, b in zip(pixel, target, strict=True))

    for name, rgb in (
        ("coral", (238, 90, 78)),
        ("amber", (243, 162, 42)),
        ("teal", (53, 190, 187)),
    ):
        assert any(near(p, rgb) for p in pixels), f"no {name} pixels in the icon"


def test_page_icon_points_at_the_file():
    assert theme.page_icon() == str(theme.FAVICON_PNG)
    assert Path(theme.page_icon()).exists()


def test_page_icon_falls_back_rather_than_crashing_the_app(monkeypatch):
    """A missing icon must not stop the app from starting."""
    monkeypatch.setattr(theme, "FAVICON_PNG", STATIC / "does-not-exist.png")
    assert theme.page_icon() == ":bar_chart:"


def test_the_icon_links_use_the_served_static_path():
    links = theme.favicon_links()
    for name in ("favicon.png", "favicon.ico", "apple-touch-icon.png"):
        assert f"/app/static/{name}" in links
    assert 'rel="icon"' in links
    assert 'rel="apple-touch-icon"' in links


def test_the_links_are_injected_with_the_stylesheet():
    """inject() is the single call the app makes, so the links must ride along with it."""
    markdown: list[str] = []
    html: list[str] = []

    class _Stub:
        def markdown(self, body, **_kwargs):
            markdown.append(body)

        def html(self, body, **_kwargs):
            html.append(body)

    theme.inject(_Stub())
    assert markdown and "/app/static/favicon.png" in markdown[0]
    assert html and "<style>" in html[0]


def test_the_stylesheet_does_not_go_through_markdown():
    """Markdown ends a raw HTML block at the first blank line, which printed the CSS
    on the page as text. The stylesheet must be sent with st.html instead."""
    markdown: list[str] = []
    html: list[str] = []

    class _Stub:
        def markdown(self, body, **_kwargs):
            markdown.append(body)

        def html(self, body, **_kwargs):
            html.append(body)

    theme.inject(_Stub())
    assert not any("<style>" in body for body in markdown)
    blank_line = chr(10) * 2
    assert blank_line not in "".join(markdown), "a blank line would end the HTML block"
    assert theme.CSS in html


def test_static_serving_is_enabled_for_the_public_directory():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "enableStaticServing = true" in config


def test_the_icons_are_shipped_in_the_container():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY static ./static" in dockerfile


def test_the_public_directory_is_not_dockerignored():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "static" not in ignored and "static/" not in ignored
