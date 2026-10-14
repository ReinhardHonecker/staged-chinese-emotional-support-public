from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ijson

from modules.risk_router import precheck_safety

TRAINING_DIR = ROOT / "data" / "training"
DEFAULT_SOURCE = TRAINING_DIR / "SoulChatCorpus-sft-multi-Turn.json"
DEFAULT_OUTPUT = TRAINING_DIR / "soulchat_sample_12000.jsonl"

DIAGNOSIS_OR_COERCION = (
    "你就是抑郁症",
    "你一定是抑郁症",
    "你有抑郁倾向",
    "你这是心理疾病",
    "你必须",
    "照我说的做",
    "不用找别人",
)
SENSITIVE = re.compile(
    r"(?:1[3-9]\d{9})|(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|"
    r"(?:微信|vx|qq)\s*[:：号]?\s*[A-Za-z0-9_-]{5,}",
    re.IGNORECASE,
)


def _chinese_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0.0
    return len(re.findall(r"[\u4e00-\u9fff]", compact)) / len(compact)


def _normalized_hash(user_text: str, response: str) -> str:
    normalized = re.sub(r"\s+", "", user_text + "\n" + response).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _valid_pair(user_text: str, response: str) -> tuple[bool, str]:
    if not (4 <= len(user_text) <= 500 and 12 <= len(response) <= 400):
        return False, "length"
    if _chinese_ratio(user_text + response) < 0.45:
        return False, "language"
    if SENSITIVE.search(user_text) or SENSITIVE.search(response):
        return False, "sensitive"
    if any(phrase in response for phrase in DIAGNOSIS_OR_COERCION):
        return False, "diagnosis_or_coercion"
    if "```" in response or len(re.findall(r"https?://", response)) > 0:
        return False, "code_or_url"
    safety = precheck_safety(user_text)
    if safety.status.value in {"S2", "S3", "S4"}:
        return False, "safety"
    return True, "accepted"


def _git_revision(source: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source.parent), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def sample(source: Path, output: Path, size: int, seed: int) -> dict:
    rng = random.Random(seed)
    reservoir: list[dict] = []
    unique_pairs: set[str] = set()
    counters: Counter[str] = Counter()
    accepted_seen = 0

    with source.open("rb") as handle:
        for conversation in ijson.items(handle, "item"):
            counters["conversations"] += 1
            conversation_id = str(conversation.get("id", counters["conversations"] - 1))
            topic = str(conversation.get("topic", "未知"))
            messages = conversation.get("messages") or []
            for index, message in enumerate(messages):
                if message.get("role") != "assistant" or index == 0:
                    continue
                previous = messages[index - 1]
                if previous.get("role") != "user":
                    counters["incomplete"] += 1
                    continue
                user_text = str(previous.get("content", "")).strip()
                response = str(message.get("content", "")).strip()
                valid, reason = _valid_pair(user_text, response)
                counters[reason] += 1
                if not valid:
                    continue
                pair_hash = _normalized_hash(user_text, response)
                if pair_hash in unique_pairs:
                    counters["duplicate"] += 1
                    continue
                unique_pairs.add(pair_hash)
                accepted_seen += 1
                context = [
                    {"role": str(item.get("role", "")), "content": str(item.get("content", ""))[:500]}
                    for item in messages[max(0, index - 5) : index]
                ]
                sample_id = hashlib.sha256(
                    f"{conversation_id}|{index}|{pair_hash}".encode("utf-8")
                ).hexdigest()[:20]
                record = {
                    "sample_id": sample_id,
                    "conversation_id": conversation_id,
                    "turn_index": index,
                    "topic": topic,
                    "context": context,
                    "current_user_text": user_text,
                    "target_response": response,
                    "source": "SoulChatCorpus",
                }
                if len(reservoir) < size:
                    reservoir.append(record)
                else:
                    replacement = rng.randrange(accepted_seen)
                    if replacement < size:
                        reservoir[replacement] = record

    if len(reservoir) != size:
        raise RuntimeError(f"过滤后只有 {len(reservoir)} 条，未达到目标 {size}")
    reservoir.sort(key=lambda item: item["sample_id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for item in reservoir:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    source_hash = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            source_hash.update(chunk)
    manifest = {
        "dataset": "SoulChatCorpus",
        "dataset_url": "https://www.modelscope.cn/datasets/YIRONGCHEN/SoulChatCorpus",
        "project_url": "https://github.com/scutcyr/SoulChat",
        "license": (
            "See THIRD_PARTY_NOTICES.md; this project applies a conservative "
            "non-commercial research and education boundary"
        ),
        "source_revision": _git_revision(source),
        "source_sha256": source_hash.hexdigest(),
        "source_size_bytes": source.stat().st_size,
        "sample_size": len(reservoir),
        "seed": seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filter_counts": dict(sorted(counters.items())),
        "sample_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(sample(args.source, args.output, args.size, args.seed), ensure_ascii=False, indent=2))
