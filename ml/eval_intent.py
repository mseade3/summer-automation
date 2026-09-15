#!/usr/bin/env python3
"""
Evaluate SMS intent classification offline.

Always runs a sklearn baseline (TF-IDF + logistic regression).
Optionally evaluates the OpenAI LLM router when OPENAI_API_KEY is set
and --llm is passed.

Usage (from repo root):
  pip install -r ml/requirements.txt
  python ml/eval_intent.py
  python ml/eval_intent.py --llm          # skip gracefully if no key
  python ml/eval_intent.py --test-size 0.3 --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

LABELS = ["BOOKING", "LEAD_INQUIRY", "UNKNOWN"]
ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "sms_intent_dataset.jsonl"
RESULTS_DIR = ROOT / "results"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("label") not in LABELS:
                raise ValueError(f"Invalid label at line {line_no}: {row.get('label')}")
            rows.append(row)
    return rows


def fmt_matrix(labels: list[str], matrix: np.ndarray) -> str:
    header = "pred→".ljust(14) + "".join(lab[:12].ljust(14) for lab in labels)
    lines = [header]
    for i, lab in enumerate(labels):
        row = lab[:12].ljust(14) + "".join(str(int(v)).ljust(14) for v in matrix[i])
        lines.append(row)
    return "\n".join(lines)


def metrics_dict(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str],
) -> dict[str, Any]:
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
        ),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(
            y_true, y_pred, labels=labels, digits=3, zero_division=0
        ),
    }


def run_sklearn(
    texts: list[str],
    labels: list[str],
    test_size: float,
    seed: int,
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    x_train, x_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=test_size,
        random_state=seed,
        stratify=labels,
    )
    pipe = Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    max_df=0.95,
                    sublinear_tf=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    random_state=seed,
                ),
            ),
        ]
    )
    pipe.fit(x_train, y_train)
    y_pred = pipe.predict(x_test).tolist()
    result = metrics_dict(y_test, y_pred, LABELS)
    result["model"] = "tfidf_logistic"
    result["train_n"] = len(x_train)
    result["test_n"] = len(x_test)
    result["train_label_counts"] = dict(Counter(y_train))
    result["test_label_counts"] = dict(Counter(y_test))
    return result, x_test, y_test, y_pred


def run_llm(texts: list[str], labels: list[str]) -> dict[str, Any] | None:
    """Evaluate production LLM router on the same texts. Returns None if skipped."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        print("LLM eval skipped: OPENAI_API_KEY not set (sklearn path still valid).")
        return None

    # Import late so sklearn-only runs never need openai installed beyond optional use.
    repo_root = ROOT.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from ai_handler import classify_incoming_intent
    except Exception as error:  # pragma: no cover - env / import issues
        print(f"LLM eval skipped: could not import ai_handler ({error}).")
        return None

    preds: list[str] = []
    errors = 0
    for text in texts:
        try:
            parsed = classify_incoming_intent(text)
            intent = str(parsed.get("intent", "UNKNOWN")).upper()
            if intent not in LABELS:
                intent = "UNKNOWN"
            preds.append(intent)
        except Exception as error:
            errors += 1
            print(f"  LLM call failed ({error}); counting as UNKNOWN.")
            preds.append("UNKNOWN")

    result = metrics_dict(labels, preds, LABELS)
    result["model"] = "openai_llm_router"
    result["errors"] = errors
    result["test_n"] = len(texts)
    return result


def print_block(title: str, metrics: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print(f"n_test     = {metrics.get('test_n', metrics.get('n'))}")
    if "train_n" in metrics:
        print(f"n_train    = {metrics['train_n']}")
    print(f"accuracy   = {metrics['accuracy']:.3f}")
    print(f"macro_f1   = {metrics['macro_f1']:.3f}")
    print(f"weighted_f1= {metrics['weighted_f1']:.3f}")
    print("\nConfusion matrix (rows=true, cols=pred):")
    print(fmt_matrix(LABELS, np.array(metrics["confusion_matrix"])))
    print("\nPer-class report:")
    print(metrics["classification_report"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SMS intent models offline.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--test-size", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Also evaluate OpenAI LLM router (skipped without OPENAI_API_KEY).",
    )
    args = parser.parse_args()

    rows = load_jsonl(args.data)
    texts = [str(r["text"]) for r in rows]
    labels = [str(r["label"]) for r in rows]
    print(f"Loaded {len(rows)} labeled SMS examples from {args.data}")
    print(f"Label counts: {dict(Counter(labels))}")
    print("Note: dataset is synthetic (see ml/data/README.md).")

    sklearn_metrics, x_test, y_test, _ = run_sklearn(
        texts, labels, test_size=args.test_size, seed=args.seed
    )
    print_block("Sklearn baseline — TF-IDF + LogisticRegression", sklearn_metrics)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "sklearn_metrics.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(sklearn_metrics, handle, indent=2)
    print(f"Wrote {out_path}")

    llm_metrics = None
    if args.llm:
        print("\nRunning optional LLM eval on the same held-out test texts...")
        llm_metrics = run_llm(x_test, y_test)
        if llm_metrics is not None:
            print_block("LLM router — OpenAI (ai_handler.classify_incoming_intent)", llm_metrics)
            llm_path = RESULTS_DIR / "llm_metrics.json"
            with llm_path.open("w", encoding="utf-8") as handle:
                json.dump(llm_metrics, handle, indent=2)
            print(f"Wrote {llm_path}")

    summary = {
        "dataset": str(args.data),
        "dataset_n": len(rows),
        "dataset_source": "synthetic",
        "seed": args.seed,
        "test_size": args.test_size,
        "sklearn": {
            "accuracy": sklearn_metrics["accuracy"],
            "macro_f1": sklearn_metrics["macro_f1"],
            "weighted_f1": sklearn_metrics["weighted_f1"],
            "confusion_matrix": sklearn_metrics["confusion_matrix"],
        },
        "llm": None
        if llm_metrics is None
        else {
            "accuracy": llm_metrics["accuracy"],
            "macro_f1": llm_metrics["macro_f1"],
            "weighted_f1": llm_metrics["weighted_f1"],
            "confusion_matrix": llm_metrics["confusion_matrix"],
            "errors": llm_metrics.get("errors", 0),
        },
    }
    summary_path = RESULTS_DIR / "eval_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
