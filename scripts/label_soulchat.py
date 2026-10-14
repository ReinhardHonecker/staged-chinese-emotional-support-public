from __future__ import annotations

import argparse
import getpass
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import LLM_TIMEOUT_SECONDS
from modules.llm_client import (
    LLMGateway,
    LLMRuntimeConfig,
    ProviderType,
    parse_json_value,
)
from modules.strategy_selector import STAGE_STRATEGIES, STRATEGIES

TRAINING_DIR = ROOT / "data" / "training"
DEFAULT_INPUT = TRAINING_DIR / "soulchat_sample_12000.jsonl"
DEFAULT_LABELS = TRAINING_DIR / "soulchat_labels_primary.jsonl"
DEFAULT_AUDIT = TRAINING_DIR / "soulchat_labels_audit.jsonl"
WRITE_LOCK = threading.Lock()
GATEWAY_LOCAL = threading.local()
RUNTIME_CONFIG: LLMRuntimeConfig | None = None

STAGE_VALUES = [stage.value for stage in STAGE_STRATEGIES if stage.value != "安全"]
STRATEGY_STAGE = {
    strategy: stage.value
    for stage, strategies in STAGE_STRATEGIES.items()
    if stage.value != "安全"
    for strategy in strategies
}

SYSTEM_PROMPT = f"""你是中文情感支持语料标注器，不是对话助手。请判断给定上下文后目标回复的主要支持动作。
只使用这些策略：{list(STRATEGIES)}。
策略对应阶段：{STRATEGY_STAGE}。
返回严格 JSON 对象：{{"labels":[...]}}。每个 label 必须包含：
sample_id、primary_strategy、secondary_candidate(null或不同策略)、applicable_stage、usable、confidence(0到1)、evidence_span、quality_flags。
quality_flags 只能取：过早建议、医学诊断、虚构经历、问题过多、方案过多、空泛、安全相关、无。
标注目标回复实际执行的动作，不要评价用户，不要改写回复。若涉及自伤他伤澄清、诊断、强迫或明显不适合作为课程支持回复，usable=false。
"""


def _load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    result = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                result.add(str(json.loads(line)["sample_id"]))
            except Exception:
                continue
    return result


def _dedupe_file(path: Path) -> None:
    if not path.exists():
        return
    unique: dict[str, dict] = {}
    for item in _load_jsonl(path):
        unique[str(item["sample_id"])] = item
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for sample_id in sorted(unique):
            handle.write(json.dumps(unique[sample_id], ensure_ascii=False) + "\n")


def _validate(item: dict, source: dict) -> dict:
    sample_id = str(item.get("sample_id", ""))
    if sample_id != source["sample_id"]:
        raise ValueError("sample_id mismatch")
    primary = str(item.get("primary_strategy", ""))
    if primary not in STRATEGIES:
        raise ValueError("invalid primary strategy")
    secondary = item.get("secondary_candidate", item.get("secondary_strategy"))
    if secondary is not None and (secondary not in STRATEGIES or secondary == primary):
        secondary = None
    stage = STRATEGY_STAGE[primary]
    evidence = str(item.get("evidence_span", ""))[:120]
    if evidence and evidence not in source["target_response"]:
        evidence = ""
    flags = [
        str(flag)
        for flag in item.get("quality_flags", [])
        if str(flag) in {"过早建议", "医学诊断", "虚构经历", "问题过多", "方案过多", "空泛", "安全相关", "无"}
    ]
    return {
        "sample_id": sample_id,
        "primary_strategy": primary,
        "secondary_candidate": secondary,
        "applicable_stage": stage,
        "usable": bool(item.get("usable", True)),
        "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.0)))),
        "evidence_span": evidence,
        "quality_flags": flags or ["无"],
    }


def _gateway(model: str) -> LLMGateway:
    if RUNTIME_CONFIG is None:
        raise RuntimeError("runtime provider configuration is missing")
    cache = getattr(GATEWAY_LOCAL, "gateways", None)
    if cache is None:
        cache = {}
        GATEWAY_LOCAL.gateways = cache
    if model not in cache:
        cache[model] = LLMGateway(RUNTIME_CONFIG.model_copy(update={"model": model}))
    return cache[model]


def _label_batch(batch: list[dict], model: str) -> list[dict]:
    payload = [
        {
            "sample_id": item["sample_id"],
            "context": item["context"],
            "target_response": item["target_response"],
        }
        for item in batch
    ]
    content = _gateway(model).call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=5000,
        json_mode=True,
    )
    parsed = parse_json_value(content)
    labels = parsed if isinstance(parsed, list) else parsed.get("labels")
    if not isinstance(labels, list):
        raise ValueError("missing labels array")
    by_id = {item["sample_id"]: item for item in batch}
    if len(labels) == len(batch):
        validated = []
        for raw_label, source in zip(labels, batch):
            raw_label["sample_id"] = source["sample_id"]
            validated.append(_validate(raw_label, source))
    else:
        validated = [
            _validate(item, by_id[str(item.get("sample_id"))])
            for item in labels
            if str(item.get("sample_id")) in by_id
        ]
    if len(validated) != len(batch):
        raise ValueError(f"batch labels incomplete: {len(validated)}/{len(batch)}")
    return validated


def _run_batches(
    records: list[dict],
    output: Path,
    model: str,
    batch_size: int,
    workers: int,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _dedupe_file(output)
    done = _completed(output)
    pending = [item for item in records if item["sample_id"] not in done]
    batches = [pending[index : index + batch_size] for index in range(0, len(pending), batch_size)]
    if not batches:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_label_batch, batch, model): batch for batch in batches}
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            for completed_count, future in enumerate(as_completed(futures), start=1):
                batch = futures[future]
                try:
                    labels = future.result()
                except Exception as exc:
                    print(f"{model}: batch_failed:{type(exc).__name__}", flush=True)
                    continue
                with WRITE_LOCK:
                    for label in labels:
                        handle.write(json.dumps(label, ensure_ascii=False) + "\n")
                    handle.flush()
                if completed_count % 20 == 0 or completed_count == len(batches):
                    print(f"{model}: {completed_count}/{len(batches)} batches", flush=True)
    _dedupe_file(output)


def _audit_records(records: list[dict], labels: list[dict], size: int, seed: int) -> list[dict]:
    by_id = {item["sample_id"]: item for item in records}
    by_class: dict[str, list[dict]] = {}
    low_confidence: list[dict] = []
    for label in labels:
        source = by_id.get(label["sample_id"])
        if not source:
            continue
        by_class.setdefault(label["primary_strategy"], []).append(source)
        if label["confidence"] < 0.70:
            low_confidence.append(source)
    rng = random.Random(seed)
    selected = {item["sample_id"]: item for item in low_confidence[:600]}
    per_class = max(1, size // max(1, len(by_class)))
    for items in by_class.values():
        rng.shuffle(items)
        for item in items[:per_class]:
            selected[item["sample_id"]] = item
    remaining = [item for item in records if item["sample_id"] not in selected]
    rng.shuffle(remaining)
    for item in remaining:
        if len(selected) >= min(1200, size + len(low_confidence)):
            break
        selected[item["sample_id"]] = item
    return list(selected.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--audit-size", type=int, default=600)
    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in ProviderType],
        default=ProviderType.OPENAI_COMPATIBLE.value,
    )
    parser.add_argument("--base-url")
    parser.add_argument("--model", required=True)
    parser.add_argument("--audit-model")
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条，用于连通性测试；0 表示全部")
    args = parser.parse_args()

    if not args.skip_audit and not args.audit_model:
        parser.error("--audit-model is required unless --skip-audit is used")
    provider = ProviderType(args.provider)
    default_urls = {
        ProviderType.OPENAI_COMPATIBLE: "https://api.openai.com/v1",
        ProviderType.ANTHROPIC: "https://api.anthropic.com",
    }
    api_key = getpass.getpass("API Key（仅保存在当前进程内存中）: ")
    RUNTIME_CONFIG = LLMRuntimeConfig(
        provider=provider,
        base_url=args.base_url or default_urls[provider],
        api_key=api_key,
        model=args.model,
        timeout_seconds=max(60.0, LLM_TIMEOUT_SECONDS),
        max_retries=2,
    )

    samples = _load_jsonl(args.input)
    if args.limit > 0:
        samples = samples[: args.limit]
    _run_batches(samples, args.labels, args.model, args.batch_size, args.workers)
    if not args.skip_audit:
        flash_labels = _load_jsonl(args.labels)
        audit_samples = _audit_records(samples, flash_labels, args.audit_size, 42)
        _run_batches(
            audit_samples,
            args.audit_output,
            args.audit_model,
            args.batch_size,
            min(4, args.workers),
        )
