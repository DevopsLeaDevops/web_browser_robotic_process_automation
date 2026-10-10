"""簡中是否由繁中重新產生、英文是否跟上繁中。規則與修正方式見 tools/i18n.py。"""

from tools.i18n import en_problems, opencc_converter, zh_hans_problems


def test_english_follows_traditional_chinese() -> None:
    problems = en_problems()
    assert not problems, "英文翻譯需要更新：\n" + "\n".join(problems)


def test_simplified_chinese_is_generated() -> None:
    problems = zh_hans_problems(opencc_converter())
    assert not problems, (
        "簡中不是最新，執行 uv run python tools/i18n.py sync 後提交：\n" + "\n".join(problems)
    )
