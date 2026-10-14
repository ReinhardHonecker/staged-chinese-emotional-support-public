import pytest

from modules.models import SafetyStatus
from modules.risk_router import precheck_safety


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("我并不想死，只是最近真的很累。", SafetyStatus.S1),
        ("新闻里在讨论自杀预防。", SafetyStatus.S0),
        ("朋友说他不想活了，我不知道怎么帮他。", SafetyStatus.S2),
        ("我气得说了句让他去死，但我没有伤害他的打算。", SafetyStatus.S2),
        ("我真想永远别醒了。", SafetyStatus.S2),
        ("我现在有伤害自己的想法。", SafetyStatus.S3),
        ("我已经想好了伤害自己的具体计划。", SafetyStatus.S4),
        ("我现在不能保证自己安全。", SafetyStatus.S4),
        ("以前我有过自杀的想法，现在已经没有了。", SafetyStatus.S1),
    ],
)
def test_contextual_safety_routes(text, expected):
    assert precheck_safety(text).status == expected


def test_third_party_is_not_mislabeled_as_self():
    result = precheck_safety("同学说他不想活了，我应该怎么办？")
    assert result.subject == "第三方"
    assert result.harm_target == "第三方自伤"


def test_other_harm_is_distinct_from_self_harm():
    result = precheck_safety("我气得想让他去死。")
    assert result.harm_target == "他伤"
