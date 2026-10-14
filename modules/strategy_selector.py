from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from config import (
    STRATEGY_CONFIDENCE_THRESHOLD,
    STRATEGY_MODEL_META_PATH,
    STRATEGY_MODEL_PATH,
    STRATEGY_SECONDARY_THRESHOLD,
    STRATEGY_SELECTOR_MODE,
)
from modules.models import (
    AdviceReadiness,
    ConversationState,
    DialogueStage,
    StrategyPrediction,
    TurnAnalysis,
)


STRATEGIES = (
    "邀请表达",
    "具体复述",
    "澄清问题",
    "总结问题地图",
    "情绪反映",
    "情绪验证",
    "力量确认",
    "短时稳定",
    "征求建议许可",
    "提供信息",
    "比较方案",
    "最小行动",
    "回顾调整",
)

STAGE_STRATEGIES: dict[DialogueStage, tuple[str, ...]] = {
    DialogueStage.EXPRESS: ("邀请表达", "具体复述", "澄清问题"),
    DialogueStage.ORGANIZE: ("具体复述", "澄清问题", "总结问题地图"),
    DialogueStage.SUPPORT: ("情绪反映", "情绪验证", "力量确认", "短时稳定"),
    DialogueStage.STRATEGIZE: ("征求建议许可", "提供信息", "比较方案"),
    DialogueStage.ACT: ("最小行动", "回顾调整"),
    DialogueStage.SAFETY: (),
}

RULE_WEIGHTS: dict[DialogueStage, dict[str, float]] = {
    DialogueStage.EXPRESS: {"具体复述": 0.48, "邀请表达": 0.34, "澄清问题": 0.18},
    DialogueStage.ORGANIZE: {"总结问题地图": 0.46, "澄清问题": 0.32, "具体复述": 0.22},
    DialogueStage.SUPPORT: {"情绪反映": 0.42, "情绪验证": 0.34, "力量确认": 0.16, "短时稳定": 0.08},
    DialogueStage.STRATEGIZE: {"比较方案": 0.50, "征求建议许可": 0.30, "提供信息": 0.20},
    DialogueStage.ACT: {"最小行动": 0.76, "回顾调整": 0.24},
    DialogueStage.SAFETY: {},
}


def _normalized(weights: dict[str, float]) -> dict[str, float]:
    positive = {key: max(0.0, float(value)) for key, value in weights.items() if value > 0}
    total = sum(positive.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in positive.items()}


def _prediction_from_weights(
    weights: dict[str, float],
    *,
    source: str,
    model_version: str,
    fallback_reason: str | None = None,
) -> StrategyPrediction:
    ordered = sorted(_normalized(weights).items(), key=lambda item: (-item[1], item[0]))
    if not ordered:
        return StrategyPrediction(
            probabilities={},
            primary_strategy="受控安全协议",
            secondary_candidate=None,
            confidence=1.0,
            source="rule",
            model_version="safety-protocol-v1",
            fallback_reason=fallback_reason or "safety_stage_bypass",
            decision_basis="controlled_safety_protocol",
        )
    primary, confidence = ordered[0]
    secondary = ordered[1][0] if len(ordered) > 1 and ordered[1][1] >= STRATEGY_SECONDARY_THRESHOLD else None
    learned_source = source in {"learned", "learned_experimental"}
    return StrategyPrediction(
        probabilities=dict(ordered) if learned_source else {},
        primary_strategy=primary,
        secondary_candidate=secondary,
        confidence=confidence if learned_source else 1.0,
        source=source,
        model_version=model_version,
        fallback_reason=fallback_reason,
        decision_basis=(
            "learned_probabilities_after_stage_mask"
            if learned_source
            else fallback_reason or "deterministic_stage_rule"
        ),
    )


def rule_prediction(stage: DialogueStage, reason: str | None = None) -> StrategyPrediction:
    return _prediction_from_weights(
        RULE_WEIGHTS[stage],
        source="rule",
        model_version="rule-v2",
        fallback_reason=reason,
    )


def build_feature_row(
    user_input: str,
    history: list[dict],
    analysis: TurnAnalysis,
    state: ConversationState,
    stage: DialogueStage,
) -> dict[str, object]:
    recent = history[-4:]
    history_text = "\n".join(
        f"{item.get('role', 'unknown')}：{str(item.get('content', ''))[:500]}" for item in recent
    )
    return {
        "text": f"{history_text}\nuser：{user_input[:1200]}",
        "stage": stage.value,
        "intent": analysis.user_intent.value,
        "readiness": analysis.advice_readiness.value,
        "emotion": analysis.primary_emotion.value,
        "intensity": str(analysis.emotion_intensity),
        "previous_strategy": state.last_strategy or "无",
        "turn_bucket": "0" if state.turn_index == 0 else "1-2" if state.turn_index <= 2 else "3+",
    }


@lru_cache(maxsize=4)
def _load_artifact(path_text: str, modified_ns: int):
    del modified_ns
    import joblib

    return joblib.load(path_text)


@lru_cache(maxsize=4)
def _verified_metadata(
    path_text: str,
    modified_ns: int,
    size_bytes: int,
    metadata_path_text: str,
    metadata_modified_ns: int,
) -> dict:
    del modified_ns, metadata_modified_ns
    path = Path(path_text)
    metadata = json.loads(Path(metadata_path_text).read_text(encoding="utf-8"))
    expected_hash = str(metadata.get("artifact_sha256", "")).lower()
    expected_size = int(metadata.get("artifact_size_bytes", -1))
    if not expected_hash or expected_size < 0:
        raise RuntimeError("strategy artifact metadata is incomplete")
    if size_bytes != expected_size:
        raise RuntimeError("strategy artifact size mismatch")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_hash:
        raise RuntimeError("strategy artifact checksum mismatch")
    return metadata


def _artifact(*, allow_unaccepted: bool = False) -> tuple[object, str, bool]:
    path = Path(STRATEGY_MODEL_PATH)
    if not path.exists():
        raise FileNotFoundError(path)
    metadata_path = Path(STRATEGY_MODEL_META_PATH)
    if not metadata_path.exists():
        raise RuntimeError("strategy artifact metadata is missing")
    stat = path.stat()
    metadata = _verified_metadata(
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
        str(metadata_path),
        metadata_path.stat().st_mtime_ns,
    )
    if not allow_unaccepted and not metadata.get("accepted", False):
        raise RuntimeError("strategy model did not pass deployment thresholds")
    loaded = _load_artifact(str(path), path.stat().st_mtime_ns)
    if isinstance(loaded, dict) and "pipeline" in loaded:
        accepted = bool(loaded.get("accepted", False))
        if not accepted and not allow_unaccepted:
            raise RuntimeError("strategy model did not pass deployment thresholds")
        return loaded["pipeline"], str(loaded.get("version", "learned-unknown")), accepted
    version = str(metadata.get("model_version", "learned-unknown"))
    return loaded, version, True


def _model_probabilities(pipeline: object, feature: dict[str, object]) -> dict[str, float]:
    import pandas as pd

    frame = pd.DataFrame([feature])
    values = pipeline.predict_proba(frame)[0]
    classes = list(pipeline.classes_)
    return {str(label): float(value) for label, value in zip(classes, values)}


def predict_strategy(
    user_input: str,
    history: list[dict],
    analysis: TurnAnalysis,
    state: ConversationState,
    stage: DialogueStage,
    selector_mode: str | None = None,
) -> StrategyPrediction:
    mode = (selector_mode or STRATEGY_SELECTOR_MODE).strip().lower()
    if mode not in {"auto", "learned", "rule"}:
        mode = "auto"
    if stage == DialogueStage.SAFETY:
        return rule_prediction(stage, "safety_stage_bypass")
    if mode == "rule":
        return rule_prediction(stage, "rule_mode_selected")
    if analysis.correction is not None:
        return rule_prediction(stage, "explicit_user_correction")
    if analysis.input_security.prompt_injection_detected:
        return rule_prediction(stage, "prompt_injection_override")

    try:
        pipeline, version, accepted = _artifact(allow_unaccepted=mode == "learned")
        raw = _model_probabilities(
            pipeline,
            build_feature_row(user_input, history, analysis, state, stage),
        )
    except Exception as exc:
        return rule_prediction(stage, f"model_unavailable:{type(exc).__name__}")

    allowed = set(STAGE_STRATEGIES[stage])
    if analysis.advice_readiness == AdviceReadiness.REJECT:
        allowed -= {"征求建议许可", "提供信息", "比较方案", "最小行动", "回顾调整"}
    masked = _normalized({key: value for key, value in raw.items() if key in allowed})
    if not masked:
        return rule_prediction(stage, "no_compatible_strategy")
    top_confidence = max(masked.values())
    if top_confidence < STRATEGY_CONFIDENCE_THRESHOLD:
        return rule_prediction(stage, f"low_confidence:{top_confidence:.3f}")
    return _prediction_from_weights(
        masked,
        source="learned" if accepted else "learned_experimental",
        model_version=version,
        fallback_reason=None if accepted else "deployment_thresholds_not_met",
    )


def strategy_model_status() -> dict[str, object]:
    path = Path(STRATEGY_MODEL_PATH)
    result: dict[str, object] = {
        "available": path.exists(),
        "path": str(path),
        "threshold": STRATEGY_CONFIDENCE_THRESHOLD,
    }
    if Path(STRATEGY_MODEL_META_PATH).exists():
        try:
            metadata_path = Path(STRATEGY_MODEL_META_PATH)
            stat = path.stat()
            metadata = _verified_metadata(
                str(path),
                stat.st_mtime_ns,
                stat.st_size,
                str(metadata_path),
                metadata_path.stat().st_mtime_ns,
            )
            result.update(metadata)
            result["integrity_verified"] = True
        except Exception:
            result["integrity_verified"] = False
            result["metadata_error"] = True
    return result
