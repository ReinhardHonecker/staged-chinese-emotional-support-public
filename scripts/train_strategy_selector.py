from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from modules.models import ConversationState, DialogueStage
from modules.state_analyzer import offline_analysis
from modules.strategy_selector import STRATEGIES, build_feature_row

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["savefig.facecolor"] = "white"

TRAINING_DIR = ROOT / "data" / "training"
ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_SAMPLES = TRAINING_DIR / "soulchat_sample_12000.jsonl"
DEFAULT_LABELS = TRAINING_DIR / "soulchat_labels_primary.jsonl"
DEFAULT_AUDIT = TRAINING_DIR / "soulchat_labels_audit.jsonl"

STAGE_MODE = {
    "表达": "我想先说说",
    "梳理": "帮我理清楚",
    "支持": "先帮我稳一下",
    "协商": "一起想办法",
    "行动": "一起想办法",
}
BAD_FLAGS = {"医学诊断", "安全相关", "过早建议", "问题过多", "方案过多"}
CAT_COLUMNS = ["stage", "intent", "readiness", "emotion", "intensity", "previous_strategy", "turn_bucket"]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _resolve_labels(flash: list[dict], audit: list[dict]) -> dict[str, dict]:
    result = {item["sample_id"]: item for item in flash}
    for item in audit:
        current = result.get(item["sample_id"])
        if current is None:
            continue
        if item.get("usable") and float(item.get("confidence", 0)) >= 0.75:
            result[item["sample_id"]] = {**item, "audited": True, "flash_strategy": current["primary_strategy"]}
        else:
            result[item["sample_id"]] = {**current, "audited": True, "audit_rejected": True}
    return result


def _accepted(label: dict) -> bool:
    if not label.get("usable", False) or float(label.get("confidence", 0)) < 0.75:
        return False
    if label.get("primary_strategy") not in STRATEGIES:
        return False
    flags = set(label.get("quality_flags", []))
    return not bool(flags & BAD_FLAGS)


def _build_frame(samples: list[dict], labels: dict[str, dict]) -> tuple[pd.DataFrame, list[str], list[str]]:
    rows: list[dict] = []
    targets: list[str] = []
    groups: list[str] = []
    for sample in samples:
        label = labels.get(sample["sample_id"])
        if label is None or not _accepted(label):
            continue
        stage = DialogueStage(label["applicable_stage"])
        state = ConversationState()
        state.turn_index = max(0, sum(item.get("role") == "user" for item in sample["context"]) - 1)
        analysis = offline_analysis(sample["current_user_text"], state, STAGE_MODE[stage.value])
        row = build_feature_row(
            sample["current_user_text"],
            sample["context"],
            analysis,
            state,
            stage,
        )
        row["sample_id"] = sample["sample_id"]
        rows.append(row)
        targets.append(label["primary_strategy"])
        groups.append(sample["conversation_id"])
    return pd.DataFrame(rows), targets, groups


def _split(frame: pd.DataFrame, labels: list[str], groups: list[str]):
    all_indices = np.arange(len(frame))
    outer = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, temp_idx = next(outer.split(all_indices, labels, groups))
    temp_groups = np.asarray(groups, dtype=object)[temp_idx]
    inner = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=42)
    val_local, test_local = next(inner.split(temp_idx, np.asarray(labels, dtype=object)[temp_idx], temp_groups))
    return train_idx, temp_idx[val_local], temp_idx[test_local]


def _pipeline(c_value: float) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            (
                "text",
                TfidfVectorizer(
                    analyzer="char",
                    ngram_range=(2, 5),
                    min_df=3,
                    max_df=0.98,
                    max_features=60000,
                    sublinear_tf=True,
                ),
                "text",
            ),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CAT_COLUMNS),
        ]
    )
    return Pipeline(
        [
            ("features", preprocessor),
            (
                "classifier",
                LogisticRegression(
                    C=c_value,
                    class_weight="balanced",
                    max_iter=600,
                    random_state=42,
                    solver="saga",
                    tol=1e-3,
                ),
            ),
        ]
    )


def _top2_accuracy(model: Pipeline, frame: pd.DataFrame, labels: list[str]) -> float:
    probabilities = model.predict_proba(frame)
    classes = np.asarray(model.classes_, dtype=object)
    top2 = classes[np.argsort(probabilities, axis=1)[:, -2:]]
    return float(np.mean([label in candidates for label, candidates in zip(labels, top2)]))


def _metrics(model: Pipeline, frame: pd.DataFrame, labels: list[str]) -> dict:
    predicted = model.predict(frame)
    return {
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_f1": float(f1_score(labels, predicted, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(labels, predicted, average="weighted", zero_division=0)),
        "top2_accuracy": _top2_accuracy(model, frame, labels),
        "classification_report": classification_report(labels, predicted, output_dict=True, zero_division=0),
    }


def train(
    samples_path: Path,
    labels_path: Path,
    audit_path: Path,
    output_dir: Path,
    teacher_model: str,
    audit_model: str,
) -> dict:
    samples = _load_jsonl(samples_path)
    flash = _load_jsonl(labels_path)
    audit = _load_jsonl(audit_path)
    flash_by_id = {item["sample_id"]: item for item in flash}
    audited_pairs = [(flash_by_id[item["sample_id"]], item) for item in audit if item["sample_id"] in flash_by_id]
    teacher_agreement = (
        sum(left["primary_strategy"] == right["primary_strategy"] for left, right in audited_pairs)
        / len(audited_pairs)
        if audited_pairs
        else None
    )
    resolved = _resolve_labels(flash, audit)
    frame, labels, groups = _build_frame(samples, resolved)
    if len(frame) < 1000:
        raise RuntimeError(f"可训练样本只有 {len(frame)} 条")
    distribution = Counter(labels)
    missing = [strategy for strategy in STRATEGIES if distribution[strategy] < 20]
    train_idx, val_idx, test_idx = _split(frame, labels, groups)
    labels_array = np.asarray(labels, dtype=object)

    candidates: list[tuple[float, float, Pipeline]] = []
    for c_value in (0.5, 1.0, 2.0):
        model = _pipeline(c_value)
        model.fit(frame.iloc[train_idx], labels_array[train_idx])
        val_pred = model.predict(frame.iloc[val_idx])
        score = float(f1_score(labels_array[val_idx], val_pred, average="macro", zero_division=0))
        candidates.append((score, c_value, model))
        print(f"C={c_value}: validation_macro_f1={score:.4f}")
    _, best_c, best_model = max(candidates, key=lambda item: (item[0], -item[1]))

    train_labels = labels_array[train_idx].tolist()
    val_labels = labels_array[val_idx].tolist()
    test_labels = labels_array[test_idx].tolist()
    test_frame = frame.iloc[test_idx]
    test_metrics = _metrics(best_model, test_frame, test_labels)
    majority = Counter(train_labels).most_common(1)[0][0]
    majority_macro = float(
        f1_score(test_labels, [majority] * len(test_labels), average="macro", zero_division=0)
    )
    group_sets = [set(np.asarray(groups, dtype=object)[indices]) for indices in (train_idx, val_idx, test_idx)]
    leakage = len(group_sets[0] & group_sets[1]) + len(group_sets[0] & group_sets[2]) + len(group_sets[1] & group_sets[2])
    accepted = (
        not missing
        and leakage == 0
        and test_metrics["macro_f1"] >= 0.55
        and test_metrics["macro_f1"] >= majority_macro + 0.10
        and test_metrics["top2_accuracy"] >= 0.75
    )

    version_seed = hashlib.sha256(
        f"{samples_path.stat().st_size}|{labels_path.stat().st_size}|{best_c}".encode("utf-8")
    ).hexdigest()[:10]
    version = f"soulchat-tfidf-logreg-v1-{version_seed}"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / "strategy_selector.joblib"
    joblib.dump(
        {"pipeline": best_model, "version": version, "accepted": accepted},
        artifact_path,
        compress=3,
    )
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    predicted = best_model.predict(test_frame)
    labels_order = [strategy for strategy in STRATEGIES if strategy in best_model.classes_]
    matrix = confusion_matrix(test_labels, predicted, labels=labels_order)
    figure, axis = plt.subplots(figsize=(12, 10))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(labels_order)), labels_order, rotation=45, ha="right")
    axis.set_yticks(range(len(labels_order)), labels_order)
    axis.set_xlabel("预测策略")
    axis.set_ylabel("真实策略")
    axis.set_title("轻量策略选择器混淆矩阵")
    figure.colorbar(image, ax=axis)
    figure.tight_layout()
    figure.savefig(output_dir / "strategy_confusion_matrix.png", dpi=180)
    plt.close(figure)

    metadata = {
        "model_version": version,
        "accepted": accepted,
        "acceptance_thresholds": {
            "macro_f1": 0.55,
            "improvement_over_majority": 0.10,
            "top2_accuracy": 0.75,
            "min_samples_per_class": 20,
        },
        "teacher_models": [teacher_model, audit_model],
        "teacher_audit": {
            "flash_count": len(flash),
            "pro_audit_count": len(audit),
            "primary_strategy_agreement": teacher_agreement,
            "pro_unusable_count": sum(not item.get("usable", False) for item in audit),
            "pro_low_confidence_count": sum(float(item.get("confidence", 0)) < 0.75 for item in audit),
        },
        "training_method": "char TF-IDF(2-5)+OneHot+balanced LogisticRegression",
        "best_c": best_c,
        "random_seed": 42,
        "sample_counts": {
            "source": len(samples),
            "accepted_for_training": len(frame),
            "train": len(train_idx),
            "validation": len(val_idx),
            "test": len(test_idx),
        },
        "class_distribution": dict(sorted(distribution.items())),
        "classes_below_minimum": missing,
        "conversation_group_leakage": leakage,
        "majority_class": majority,
        "majority_macro_f1": majority_macro,
        "validation_candidates": [
            {"c": c_value, "macro_f1": score} for score, c_value, _ in candidates
        ],
        "test_metrics": test_metrics,
        "artifact_sha256": artifact_hash,
        "artifact_size_bytes": artifact_path.stat().st_size,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "strategy_selector_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "strategy_selector_metrics.json").write_text(
        json.dumps(test_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source_manifest = samples_path.with_suffix(".manifest.json")
    if source_manifest.exists():
        (output_dir / "strategy_data_manifest.json").write_text(
            source_manifest.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--teacher-model", required=True)
    parser.add_argument("--audit-model", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            train(
                args.samples,
                args.labels,
                args.audit,
                args.output_dir,
                args.teacher_model,
                args.audit_model,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
