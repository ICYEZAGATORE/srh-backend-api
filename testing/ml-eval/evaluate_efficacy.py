"""
Step 5 (efficacy) — evaluate the three DEPLOYED classifiers on held-out test data.

Loads the exact production artifacts from ``srh-backend-api/models/*.pkl`` and the
held-out test splits from the ``srh-ml-model`` repo, then reports per-class and
macro precision / recall / F1, accuracy, and a confusion matrix for each model.
Recorded baselines (from each model's *_metadata.json) are printed alongside the
freshly-measured numbers to confirm consistency after the scikit-learn / XGBoost
version-pinning fix.

No model is retrained here — this measures what is actually shipped. Run:

    venv/Scripts/python.exe testing/ml-eval/evaluate_efficacy.py

Outputs (testing/ml-eval/results/):
  - efficacy_results.md           (tables, per model, vs baseline)
  - efficacy_metrics.json         (machine-readable)
  - confusion_<model>.png         (heatmaps)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
)

BACKEND = Path(__file__).resolve().parents[2]          # srh-backend-api
ML = BACKEND.parent / "srh-ml-model"                   # sibling data repo
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(parents=True, exist_ok=True)

# model pkl, metadata json, test csv, text col, label col, class names (index order)
MODELS = {
    "safety": dict(
        pkl=BACKEND / "models/safety_classifier.pkl",
        meta=BACKEND / "models/safety_classifier_metadata.json",
        csv=ML / "data/Safety/safety_test.csv",
        text="text", label="label", classes=["safe", "unsafe"],
    ),
    "topic": dict(
        pkl=BACKEND / "models/topic_classifier_B.pkl",
        meta=BACKEND / "models/topic_classifier_B_metadata.json",
        csv=ML / "data/Topic_Classifier_data/topic_test.csv",
        text="text", label="label",
        classes=["contraception", "sti_hiv", "pregnancy", "puberty",
                 "gbv_consent", "disability_srh", "general_srh"],
    ),
    "language": dict(
        pkl=BACKEND / "models/language_classifier.pkl",
        meta=BACKEND / "models/language_classifier_metadata.json",
        csv=ML / "data/Language_Classifier_data/lang_test.csv",
        text="text", label="label", classes=["english", "kinyarwanda"],
    ),
}


def evaluate(name: str, cfg: dict) -> dict:
    model = joblib.load(cfg["pkl"])
    df = pd.read_csv(cfg["csv"])
    X = df[cfg["text"]].astype(str).tolist()
    y_true = df[cfg["label"]].astype(int).tolist()
    y_pred = [int(p) for p in model.predict(X)]

    classes = cfg["classes"]
    labels = list(range(len(classes)))
    report = classification_report(
        y_true, y_pred, labels=labels, target_names=classes,
        output_dict=True, zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    # confusion-matrix heatmap
    fig, ax = plt.subplots(figsize=(1.6 + 1.1 * len(classes), 1.4 + 0.9 * len(classes)))
    sns.heatmap(cm, annot=True, fmt="d", cmap="crest", cbar=False,
                xticklabels=classes, yticklabels=classes, ax=ax)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    ax.set_title(f"{name} — confusion matrix (n={len(y_true)})")
    plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
    fig.tight_layout()
    fig.savefig(OUT / f"confusion_{name}.png", dpi=130)
    plt.close(fig)

    meta = json.loads(Path(cfg["meta"]).read_text(encoding="utf-8"))
    return dict(
        name=name, n=len(y_true),
        accuracy=accuracy_score(y_true, y_pred),
        f1_macro=f1_score(y_true, y_pred, average="macro", zero_division=0),
        report=report, confusion=cm.tolist(), classes=classes,
        baseline=meta.get("test_metrics", {}),
    )


def md_table(res: dict) -> str:
    r = res["report"]
    lines = [f"### {res['name']}  (n = {res['n']})", "",
             "| class | precision | recall | f1 | support |",
             "|---|---|---|---|---|"]
    for c in res["classes"]:
        row = r[c]
        lines.append(f"| {c} | {row['precision']:.3f} | {row['recall']:.3f} "
                     f"| {row['f1-score']:.3f} | {int(row['support'])} |")
    lines.append(f"| **macro avg** | {r['macro avg']['precision']:.3f} | "
                 f"{r['macro avg']['recall']:.3f} | {r['macro avg']['f1-score']:.3f} "
                 f"| {int(r['macro avg']['support'])} |")
    lines.append("")
    lines.append(f"- **Accuracy (measured):** {res['accuracy']:.4f}  ·  "
                 f"**Macro-F1 (measured):** {res['f1_macro']:.4f}")
    base = res["baseline"]
    if base:
        b = ", ".join(f"{k}={v}" for k, v in base.items())
        lines.append(f"- **Recorded baseline (test_metrics):** {b}")
    lines.append(f"- Confusion matrix: `results/confusion_{res['name']}.png`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    results = {name: evaluate(name, cfg) for name, cfg in MODELS.items()}
    (OUT / "efficacy_metrics.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")

    md = ["# Step 5 — ML Efficacy (held-out test sets)", "",
          "Deployed artifacts (`srh-backend-api/models/*.pkl`) evaluated on the "
          "`srh-ml-model` held-out test splits. Models are **not** retrained here.",
          ""]
    for name in MODELS:
        md.append(md_table(results[name]))
    (OUT / "efficacy_results.md").write_text("\n".join(md), encoding="utf-8")

    print("EFFICACY SUMMARY")
    for name, r in results.items():
        base = r["baseline"]
        print(f"  {name:9s} n={r['n']:5d}  acc={r['accuracy']:.4f}  "
              f"macroF1={r['f1_macro']:.4f}  (baseline acc="
              f"{base.get('accuracy','?')}, f1_macro={base.get('f1_macro','?')})")
    print(f"\nWrote {OUT/'efficacy_results.md'} + confusion_*.png")


if __name__ == "__main__":
    main()
