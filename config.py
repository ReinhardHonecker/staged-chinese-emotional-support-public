import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PROMPT_DIR = PROJECT_ROOT / "prompts"
DATA_DIR = PROJECT_ROOT / "data"
RESOURCE_DIR = PROJECT_ROOT / "resources"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"

# Provider credentials and model choices are intentionally not read from files
# or environment variables. They are supplied through the Streamlit UI and kept
# only in the current session.
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

ANALYSIS_TEMPERATURE = 0.1
RESPONSE_TEMPERATURE = 0.6
GUARD_TEMPERATURE = 0.0
ANALYSIS_MAX_TOKENS = 2600
RESPONSE_MAX_TOKENS = 1000
GUARD_MAX_TOKENS = 1600

MAX_HISTORY_ROUNDS = 6
MAX_USER_INPUT_LENGTH = 1200
MAX_HISTORY_CHARS = 6000

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"
METRICS_DB_PATH = DATA_DIR / "runtime_metrics.sqlite3"
SAFETY_RESOURCE_PATH = RESOURCE_DIR / "safety_resources_zh_CN.json"
STRATEGY_MODEL_PATH = ARTIFACT_DIR / "strategy_selector.joblib"
STRATEGY_MODEL_META_PATH = ARTIFACT_DIR / "strategy_selector_metadata.json"
STRATEGY_SELECTOR_MODE = os.getenv("STRATEGY_SELECTOR_MODE", "auto").strip().lower()
if STRATEGY_SELECTOR_MODE not in {"auto", "learned", "rule"}:
    STRATEGY_SELECTOR_MODE = "auto"
STRATEGY_CONFIDENCE_THRESHOLD = float(os.getenv("STRATEGY_CONFIDENCE_THRESHOLD", "0.45"))
STRATEGY_SECONDARY_THRESHOLD = float(os.getenv("STRATEGY_SECONDARY_THRESHOLD", "0.20"))

STAGE_LENGTH_LIMITS = {
    "表达": (50, 120),
    "梳理": (80, 160),
    "支持": (80, 180),
    "协商": (130, 260),
    "行动": (120, 240),
    "安全": (50, 140),
}

# These lists are only a local attention pre-check. They do not constitute a
# clinical assessment and must not decide the final routing without context.
DIRECT_SELF_HARM_PHRASES = [
    "不想活",
    "想死",
    "自杀",
    "结束生命",
    "伤害自己",
    "割腕",
    "跳楼",
    "活不下去",
    "再也不想醒来",
]

INDIRECT_CRISIS_PHRASES = [
    "想消失",
    "永远别醒",
    "活着没意义",
    "没有希望",
    "撑不下去",
    "坚持不住",
    "受不了了",
]

HIGH_DISTRESS_PHRASES = [
    "很绝望",
    "没人关心我",
    "我好痛苦",
    "特别崩溃",
    "完全无助",
    "被困住",
    "快耗尽",
    "喘不过气",
    "特别慌",
    "很难受",
]
