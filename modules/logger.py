"""Raw dialogue logging was intentionally removed.

Runtime evaluation metrics are handled by ``modules.metrics`` and never store
user text or model responses.
"""


def save_dialogue_log(*_args, **_kwargs):
    raise RuntimeError("原始对话日志已禁用；不得持久化用户原文。")
