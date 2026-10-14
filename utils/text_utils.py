import re

from config import MAX_HISTORY_CHARS, MAX_USER_INPUT_LENGTH


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u200b", "").strip()
    return re.sub(r"[ \t]+", " ", text)


def truncate_text(text: str, max_length: int = MAX_USER_INPUT_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    marker = "……[中间内容因长度限制省略]……"
    remaining = max_length - len(marker)
    head_length = int(remaining * 0.65)
    tail_length = remaining - head_length
    return text[:head_length] + marker + text[-tail_length:]


def normalize_for_rules(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?;；:：‘’“”\"']+", "", text.lower())


def format_history(history: list[dict], max_chars: int = MAX_HISTORY_CHARS) -> str:
    if not history:
        return "无"
    lines = []
    for message in history:
        role = message.get("role", "")
        content = clean_text(message.get("content", ""))
        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"助手：{content}")
    result = "\n".join(lines)
    return result[-max_chars:]


def count_questions(text: str) -> int:
    # Questions inside quoted drafts, cited user language or code are not
    # questions the assistant asks the current user.
    without_quotes = text
    for pattern in [
        r"“[^”]*”",
        r"‘[^’]*’",
        r"\"[^\"]*\"",
        r"'[^']*'",
        r"`[^`]*`",
    ]:
        without_quotes = re.sub(pattern, "", without_quotes)
    return without_quotes.count("？") + without_quotes.count("?")


def visible_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))
