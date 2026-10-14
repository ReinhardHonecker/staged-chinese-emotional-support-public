import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


DOCUMENT_MARKERS = {
    "README.md": [
        ("Overview", "项目概述"),
        ("Key capabilities", "主要能力"),
        ("Installation and launch", "安装与运行"),
        ("Compliance, provenance, and citation", "合规、来源与引用"),
    ],
    "EVALUATION.md": [
        ("Evaluation Protocol", "评测协议"),
        ("Explicit UI-mode adherence", "显式 UI 模式遵循"),
        ("Blind stage routing", "无模式提示的盲阶段分流"),
        ("Response checks", "回复检查"),
    ],
    "MODEL_CARD.md": [
        ("Summary", "概要"),
        ("Training provenance", "训练来源"),
        ("Intended use", "预期用途"),
        ("Limitations", "局限"),
    ],
    "PRIVACY_AND_SAFETY.md": [
        ("Default behavior", "默认行为"),
        ("Optional online mode", "可选在线模式"),
        ("Safety routing", "安全分流"),
    ],
    "THIRD_PARTY_NOTICES.md": [
        ("Third-party Notices", "第三方声明"),
        ("Historical teacher annotation", "历史教师标注"),
        ("Runtime SDKs", "运行时 SDK"),
    ],
    "PUBLIC_RELEASE_CHECKLIST.md": [
        ("Public-release Hold Checklist", "暂缓公开发布检查表"),
        ("Reconfirm permission", "重新确认是否获准"),
        ("Obtain fresh, explicit approval", "重新取得明确授权"),
    ],
}


def test_reader_facing_documents_are_bilingual_with_english_first():
    for relative_path, pairs in DOCUMENT_MARKERS.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for english, chinese in pairs:
            assert english in text, (relative_path, english)
            assert chinese in text, (relative_path, chinese)
            assert text.index(english) < text.index(chinese), (
                relative_path,
                english,
                chinese,
            )


def test_citation_and_ci_visible_labels_are_bilingual():
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert "Staged Chinese Emotional Support / 分阶段中文情感支持" in citation
    assert citation.index("If you use this course project") < citation.index("如果使用本课程项目")

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "Tests / 测试" in workflow
    assert "Install dependencies / 安装依赖" in workflow
    assert (
        "Run tests without provider credentials / 无服务商凭据运行测试"
        in workflow
    )
    assert "Generate offline evaluation report / 生成离线评测报告" in workflow
    assert "Upload offline evaluation report / 上传离线评测报告" in workflow


def test_official_license_text_remains_unmodified_and_documented_as_exception():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("# PolyForm Noncommercial License 1.0.0")
    assert "Required Notice: Copyright 2026 ReinhardHonecker" in license_text

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "official `LICENSE` text remains unchanged" in readme
    assert "官方 `LICENSE` 正文保持原样" in readme


def test_local_links_in_reader_facing_documents_resolve():
    for relative_path in DOCUMENT_MARKERS:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#")):
                continue
            assert (ROOT / target).exists(), (relative_path, target)
