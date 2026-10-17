"""
Part A - Fraud detection prototype (PayGuard)

What this script does, top to bottom:
  1. Load creditcard.csv and drop exact duplicate rows.
  2. Split by TIME (oldest 60% train, next 20% validation, newest 20% test),
     because in production we always predict the future from the past.
  3. Train two models:
       - baseline: logistic regression
       - stronger: gradient-boosted trees (sklearn HistGradientBoosting)
  4. Pick the alert threshold on the VALIDATION set by minimising money lost
     (missed fraud amount + cost of reviewing false alarms).
  5. Report everything on the untouched TEST set and save plots + a summary.

Run:  python fraud.py   (from this folder, or press the Run button in VS Code)
Everything you might want to change is in the SETTINGS block below.
"""

import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save plots to files, no window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------- SETTINGS
ROOT = Path(__file__).resolve().parent   # the folder this file is in
DATA_FILE = ROOT / "data" / "creditcard.csv"
RESULTS_DIR = ROOT / "results"

TRAIN_SHARE = 0.60        # oldest 60% of transactions
VALID_SHARE = 0.20        # next 20% (used only to choose the threshold)
                          # the newest 20% is the test set

REVIEW_COST = 5.0         # assumed cost ($) of one false alarm: analyst time + annoyed customer
REVIEW_COSTS_TO_COMPARE = [1.0, 5.0, 25.0]  # sensitivity check: how the threshold moves with this assumption
# The cost of a missed fraud is the transaction amount itself (money we lose).

RANDOM_SEED = 42
N_BOOTSTRAP = 1000        # resamples used for the confidence interval on the test set
# ------------------------------------------------------------------------


def load_data():
    if not DATA_FILE.exists():
        raise SystemExit(f"Data file not found: {DATA_FILE}\n"
                         "Download creditcard.csv from Kaggle and put it in the 'data' folder (see README.md).")
    df = pd.read_csv(DATA_FILE)
    n_before = len(df)
    df = df.drop_duplicates()  # 1,081 exact duplicate rows would otherwise leak across splits
    print(f"Loaded {n_before:,} rows, {n_before - len(df):,} duplicates removed, "
          f"{df['Class'].sum()} frauds ({df['Class'].mean():.3%})")
    return df.sort_values("Time").reset_index(drop=True)


def make_features(df):
    """V1..V28 are already-anonymised PCA features. We add log(amount).
    'Time' is dropped: it is 'seconds since the first transaction in this file',
    which means nothing for a live transaction (see README)."""
    features = df[[f"V{i}" for i in range(1, 29)]].copy()
    features["log_amount"] = np.log1p(df["Amount"])
    return features


def time_split(df):
    n = len(df)
    train_end = int(n * TRAIN_SHARE)
    valid_end = int(n * (TRAIN_SHARE + VALID_SHARE))
    return df.iloc[:train_end], df.iloc[train_end:valid_end], df.iloc[valid_end:]


def build_models():
    return {
        # Simple, explainable, fast. class_weight makes it pay attention to the rare fraud class.
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=2000),
        ),
        # Trees capture non-linear patterns and feature interactions.
        # Note: sklearn's DEFAULT settings were unstable here (PR-AUC 0.29 on validation): with only
        # ~340 frauds, built-in early stopping quit after 11 rounds and unregularised leaves overfit.
        # Fix = smaller trees + L2 penalty + no early stopping. Picked from 4 settings on VALIDATION
        # data only (see README) - no heavy tuning, as the brief asks.
        "gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=300,
            max_leaf_nodes=15,
            min_samples_leaf=50,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=RANDOM_SEED,
        ),
    }


def money_cost(y_true, scores, amounts, threshold, review_cost=REVIEW_COST):
    """Total $ cost of using this threshold = missed fraud amounts + review_cost per false alarm."""
    flagged = scores >= threshold
    missed_fraud = (~flagged) & (y_true == 1)
    false_alarm = flagged & (y_true == 0)
    return amounts[missed_fraud].sum() + review_cost * false_alarm.sum()


def best_threshold(y_true, scores, amounts, review_cost=REVIEW_COST):
    """Try many thresholds and keep the one with the lowest $ cost."""
    candidates = np.unique(np.quantile(scores, np.linspace(0.90, 1.0, 2001)))
    costs = [money_cost(y_true, scores, amounts, t, review_cost) for t in candidates]
    best = int(np.argmin(costs))
    return candidates[best], candidates, costs


def bootstrap_pr_auc(y_true, scores):
    """95% interval for PR-AUC. The test set has only ~90 frauds, so the number is noisy."""
    rng = np.random.default_rng(RANDOM_SEED)
    values = []
    for _ in range(N_BOOTSTRAP):
        idx = rng.integers(0, len(y_true), len(y_true))
        if y_true[idx].sum() > 0:
            values.append(average_precision_score(y_true[idx], scores[idx]))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def paired_bootstrap_difference(y_true, scores_a, scores_b):
    """95% interval for PR-AUC(b) - PR-AUC(a), resampling the SAME rows for both models.
    If the interval excludes 0, model b is better on this test set beyond sampling noise."""
    rng = np.random.default_rng(RANDOM_SEED)
    diffs = []
    for _ in range(N_BOOTSTRAP):
        idx = rng.integers(0, len(y_true), len(y_true))
        if y_true[idx].sum() > 0:
            diffs.append(average_precision_score(y_true[idx], scores_b[idx])
                         - average_precision_score(y_true[idx], scores_a[idx]))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def report_at_threshold(y_true, scores, amounts, threshold):
    flagged = scores >= threshold
    tp = int((flagged & (y_true == 1)).sum())
    fp = int((flagged & (y_true == 0)).sum())
    fn = int((~flagged & (y_true == 1)).sum())
    fraud_total = amounts[y_true == 1].sum()
    fraud_caught = amounts[flagged & (y_true == 1)].sum()
    return {
        "threshold": float(threshold),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "alerts_per_10k_transactions": 10_000 * flagged.mean(),
        "fraud_amount_caught_share": float(fraud_caught / fraud_total),
        "total_cost_usd": float(money_cost(y_true, scores, amounts, threshold)),
        "cost_if_no_model_usd": float(fraud_total),  # do nothing = lose every fraud
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    df = load_data()
    train, valid, test = time_split(df)
    for name, part in [("train", train), ("valid", valid), ("test", test)]:
        print(f"  {name:5s}: {len(part):7,} rows, {part['Class'].sum():3d} frauds")

    X_train, y_train = make_features(train), train["Class"].to_numpy()
    X_valid, y_valid, amt_valid = make_features(valid), valid["Class"].to_numpy(), valid["Amount"].to_numpy()
    X_test, y_test, amt_test = make_features(test), test["Class"].to_numpy(), test["Amount"].to_numpy()

    results = {}
    test_scores_by_model = {}
    fig_pr, ax_pr = plt.subplots(figsize=(6, 5))
    fig_cost, ax_cost = plt.subplots(figsize=(6, 5))

    for name, model in build_models().items():
        print(f"\nTraining {name} ...")
        model.fit(X_train, y_train)

        # 1) choose threshold on validation data only
        valid_scores = model.predict_proba(X_valid)[:, 1]
        threshold, candidates, costs = best_threshold(y_valid, valid_scores, amt_valid)

        # 2) evaluate once on the test data
        test_scores = model.predict_proba(X_test)[:, 1]
        test_scores_by_model[name] = test_scores
        start = time.perf_counter()
        for i in range(200):  # latency of scoring ONE transaction, like a live API call
            model.predict_proba(X_test.iloc[[i]])
        latency_ms = (time.perf_counter() - start) / 200 * 1000

        sensitivity = []
        for review_cost in REVIEW_COSTS_TO_COMPARE:
            t, _, _ = best_threshold(y_valid, valid_scores, amt_valid, review_cost)
            flagged = test_scores >= t
            sensitivity.append({
                "review_cost": review_cost,
                "threshold": float(t),
                "test_recall": float((flagged & (y_test == 1)).sum() / y_test.sum()),
                "test_false_alarms": int((flagged & (y_test == 0)).sum()),
            })

        results[name] = {
            "test_pr_auc": float(average_precision_score(y_test, test_scores)),
            "test_pr_auc_95ci": bootstrap_pr_auc(y_test, test_scores),
            "test_roc_auc": float(roc_auc_score(y_test, test_scores)),
            "at_chosen_threshold": report_at_threshold(y_test, test_scores, amt_test, threshold),
            "single_prediction_latency_ms": latency_ms,
            "review_cost_sensitivity": sensitivity,
        }

        precision, recall, _ = precision_recall_curve(y_test, test_scores)
        ax_pr.plot(recall, precision, label=f"{name} (PR-AUC {results[name]['test_pr_auc']:.2f})")
        ax_cost.plot(candidates, costs, label=name)
        ax_cost.axvline(threshold, linestyle=":", color=ax_cost.lines[-1].get_color())

    ax_pr.set(xlabel="Recall (share of frauds caught)", ylabel="Precision (share of alerts that are fraud)",
              title="Test set precision-recall")
    ax_pr.legend()
    fig_pr.savefig(RESULTS_DIR / "part_a_pr_curve.png", dpi=120, bbox_inches="tight")

    ax_cost.set(xscale="log", xlabel="Threshold (log scale)", ylabel="Total cost on validation ($)",
                title=f"Choosing the threshold (false alarm = ${REVIEW_COST:.0f})")
    ax_cost.legend()
    fig_cost.savefig(RESULTS_DIR / "part_a_cost_vs_threshold.png", dpi=120, bbox_inches="tight")

    results["pr_auc_gain_boosting_minus_logistic_95ci"] = paired_bootstrap_difference(
        y_test, test_scores_by_model["logistic_regression"], test_scores_by_model["gradient_boosting"])

    with open(RESULTS_DIR / "part_a_metrics.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== TEST SET RESULTS ===")
    for name in build_models():
        r = results[name]
        t = r["at_chosen_threshold"]
        lo, hi = r["test_pr_auc_95ci"]
        print(f"{name}: PR-AUC {r['test_pr_auc']:.3f} (95% CI {lo:.3f}-{hi:.3f}), ROC-AUC {r['test_roc_auc']:.3f}")
        print(f"   at threshold {t['threshold']:.4f}: precision {t['precision']:.2f}, recall {t['recall']:.2f}, "
              f"TP {t['true_positives']}, FP {t['false_positives']}, FN {t['false_negatives']}")
        print(f"   cost ${t['total_cost_usd']:,.0f} vs ${t['cost_if_no_model_usd']:,.0f} with no model, "
              f"{t['alerts_per_10k_transactions']:.1f} alerts per 10k txns, latency {r['single_prediction_latency_ms']:.1f} ms")
        for row in r["review_cost_sensitivity"]:
            print(f"   if a false alarm costs ${row['review_cost']:>4.0f}: threshold {row['threshold']:.4f}, "
                  f"recall {row['test_recall']:.2f}, false alarms {row['test_false_alarms']}")
    lo, hi = results["pr_auc_gain_boosting_minus_logistic_95ci"]
    print(f"\nPR-AUC gain of boosting over logistic regression, paired 95% CI: {lo:+.3f} to {hi:+.3f}")
    print(f"\nSaved metrics and plots to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
