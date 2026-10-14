from pathlib import Path
import re
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIDEBAR = 'section[data-testid="stSidebar"]'
SIDEBAR_TEXT_FALLBACKS = {
    f'{SIDEBAR} [data-testid="stWidgetLabel"]': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stWidgetLabel"] p': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stCheckbox"] label': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stExpander"] summary': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stTextInput"] input': "var(--ink-800)",
    f'{SIDEBAR} [data-testid="stCaptionContainer"]': "var(--ink-600)",
    f'{SIDEBAR} [data-testid="stCaptionContainer"] p': "var(--ink-600)",
    f'{SIDEBAR} [data-testid="stTextInput"] input::placeholder': "var(--ink-600)",
}


def test_project_theme_uses_light_base_and_explicit_sidebar_palette():
    config_path = PROJECT_ROOT / ".streamlit" / "config.toml"
    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["theme"]["base"] == "light"
    assert config["theme"]["sidebar"] == {
        "backgroundColor": "#f6f6fc",
        "secondaryBackgroundColor": "#ffffff",
        "textColor": "#363b55",
        "primaryColor": "#7568b8",
    }


def sidebar_foreground_rules():
    css_path = PROJECT_ROOT / "assets" / "app.css"
    assert css_path.is_file()
    css = re.sub(r"/\*.*?\*/", "", css_path.read_text(encoding="utf-8"), flags=re.S)
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        color = re.search(r"(?:^|;)\s*color\s*:\s*([^;]+)", declarations)
        if color:
            for selector in selectors.split(","):
                if "stSidebar" in selector:
                    yield selector.strip(), color.group(1).strip()


def test_sidebar_text_widgets_have_scoped_color_fallbacks():
    actual = dict(sidebar_foreground_rules())
    for selector, color in SIDEBAR_TEXT_FALLBACKS.items():
        assert actual.get(selector) == f"{color} !important", selector


def test_sidebar_color_overrides_do_not_target_buttons_status_or_all_descendants():
    # An allowlist prevents a broad sidebar color rule from overriding native
    # primary buttons or the intentionally distinct Online / Offline pills.
    for selector, _ in sidebar_foreground_rules():
        assert selector in SIDEBAR_TEXT_FALLBACKS, selector
        assert "*" not in selector
        assert "button" not in selector
        assert "runtime-pill" not in selector
