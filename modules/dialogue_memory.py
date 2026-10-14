"""Legacy module retained only to fail loudly if old code imports it.

Conversation history must live in ``st.session_state``. A module-level list
would leak messages across Streamlit sessions.
"""


def _removed(*_args, **_kwargs):
    raise RuntimeError("全局对话记忆已移除；请使用当前 Streamlit 会话的 messages。")


add_message = _removed
get_recent_history = _removed
clear_history = _removed
