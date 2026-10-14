import json
import os


def read_text_file(path: str) -> str:
    """
    读取文本文件。
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path: str):
    """
    读取 JSON 文件。
    如果文件不存在，则返回空列表。
    """
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except Exception:
        return []


def save_json(path: str, data):
    """
    保存 JSON 文件。
    """
    directory = os.path.dirname(path)

    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)