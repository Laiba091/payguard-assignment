"""
Part B, step 3 - evaluate the triage results.

Reads:
    results/part_b_triage.jsonl        (from triage.py, all 400 complaints)
    data/hand_labels.csv               (60 complaints labelled by hand - the "gold" answers)
    results/part_b_adversarial.jsonl   (optional, from running triage.py on the adversarial set)
Writes:
    results/part_b_evaluation.md       (all numbers used in the README)
    results/summary_review.csv         (summaries next to the complaint text, for a human to check)

What "correct" means here:
    category        strict  = equals the hand label
                    lenient = equals the hand label OR the acceptable alternative (complaints can
                              honestly belong to two queues, e.g. identity theft on a credit report)
    urgency         exact match, and "high" recall (missing a high-urgency case is the costly error)
    requires_human  RECALL is the safety metric: every complaint that a human must see should be
                    flagged. A miss here can mean a fraud or legal case is auto-closed.

Run:  python evaluate.py
"""

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent   # the folder this file is in
PREDICTIONS_FILE = ROOT / "results" / "part_b_triage.jsonl"
ADVERSARIAL_FILE = ROOT / "results" / "part_b_adversarial.jsonl"
HAND_LABELS_FILE = ROOT / "data" / "hand_labels.csv"
SAMPLE_FILE = ROOT / "data" / "complaints_sample.csv"
ADVERSARIAL_INPUT = ROOT / "data" / "adversarial_complaints.csv"
REPORT_FILE = ROOT / "results" / "part_b_evaluation.md"
SUMMARY_REVIEW_FILE = ROOT / "results" / "summary_review.csv"

# Prices for the default model gemini-3.1-flash-lite, USD per 1 million tokens
# (ai.google.dev/gemini-api/docs/pricing, checked 2026-10-16). Change these if you change model.
PRICE_INPUT_PER_MILLION = 0.25
PRICE_OUTPUT_PER_MILLION = 1.50
COMPLAINTS_PER_MONTH = 50_000

# CFPB "product" -> the category we would expect. Used only as a rough, automatic check on all
# 400 complaints (the product is chosen by the consumer and often doesn't match the real issue).
PRODUCT_TO_CATEGORY = {
    "Credit reporting or other personal consumer reports": "credit_reporting",
    "Debt collection": "debt_collection",
    "Checking or savings account": "bank_accounts",
    "Credit card": "credit_cards",
    "Money transfer, virtual currency, or money service": "payments_transfers",
    "Prepaid card": "payments_transfers",
    "Mortgage": "loans",
    "Student loan": "loans",
    "Vehicle loan or lease": "loans",
    "Payday loan, title loan, personal loan, or advance loan": "loans",
    "Debt or credit management": "loans",
}


def counts_table(values, column_name):
    """Small markdown table of value counts (avoids an extra dependency)."""
    counts = pd.Series(values).value_counts()
    if counts.empty:
        return "(none)"
    rows = [f"| {name} | {count} |" for name, count in counts.items()]
    return "\n".join([f"| {column_name} | complaints |", "|---|---|"] + rows)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return pd.DataFrame([json.loads(line) for line in f if line.strip()])


def wilson_interval(successes, total):
    """95% confidence interval for a proportion. With only 60 labels, this matters."""
    if total == 0:
        return 0.0, 0.0
    z = 1.96
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return centre - margin, centre + margin


def pct(successes, total):
    low, high = wilson_interval(successes, total)
    return f"{successes}/{total} = {successes / max(total, 1):.0%} (95% CI {low:.0%}-{high:.0%})"


def reliability_section(preds):
    ok = preds["status"] == "ok"
    retried = ok & (preds["attempts"] > 1)
    return [
        "## 1. Reliability (all complaints)",
        f"- Valid structured record: {pct(int(ok.sum()), len(preds))}",
        f"- Needed a retry to get valid JSON: {int(retried.sum())}",
        f"- Failed after all retries (sent to manual triage): {int((~ok).sum())}",
        f"- Median seconds per complaint: {preds['seconds'].median():.1f}",
        "",
    ]


def hand_label_section(preds, labels):
    # Failed records are kept: they count as wrong on category/urgency, but they DID go to a human.
    df = labels.merge(preds, on="complaint_id", suffixes=("_gold", "_pred"))
    n = len(df)
    gold_human = df["requires_human_gold"].astype(str).str.lower() == "true"

    strict = df["category_gold"] == df["category_pred"]
    lenient = strict | (df["alt_category"].fillna("") == df["category_pred"])
    urgency_exact = df["urgency_gold"] == df["urgency_pred"]
    gold_high = df["urgency_gold"] == "high"

    llm_flag = df["llm_requires_human"].fillna(False).astype(bool)
    final_flag = df["requires_human_pred"].astype(bool)

    lines = [
        f"## 2. Accuracy against {n} hand-labelled complaints",
        f"- Category, strict: {pct(int(strict.sum()), n)}",
        f"- Category, lenient (alternative also accepted): {pct(int(lenient.sum()), n)}",
        f"- Urgency, exact: {pct(int(urgency_exact.sum()), n)}",
        f"- Urgency, high-urgency cases caught: {pct(int((gold_high & (df['urgency_pred'] == 'high')).sum()), int(gold_high.sum()))}",
        f"- requires_human RECALL, LLM alone: {pct(int((gold_human & llm_flag).sum()), int(gold_human.sum()))}",
        f"- requires_human RECALL, LLM + guardrails (final): {pct(int((gold_human & final_flag).sum()), int(gold_human.sum()))}",
        f"- requires_human precision (final): {pct(int((gold_human & final_flag).sum()), int(final_flag.sum()))}",
        "",
        "Per-category recall (strict):",
        "",
        "| category | labelled | correct |",
        "|---|---|---|",
    ]
    for category, group in df.groupby("category_gold"):
        lines.append(f"| {category} | {len(group)} | {int((group['category_pred'] == category).sum())} |")

    missed = df[gold_human & ~final_flag]
    lines += ["", f"**Sensitive complaints NOT sent to a human (must be 0): {len(missed)}**"]
    for row in missed.itertuples():
        lines.append(f"- {row.complaint_id}: {row.label_note}")

    wrong = df[~lenient]
    lines += ["", "Category errors (gold -> predicted):"]
    for row in wrong.itertuples():
        lines.append(f"- {row.complaint_id}: {row.category_gold} -> {row.category_pred}  ({row.label_note})")
    lines.append("")
    return lines


def silver_section(preds, sample):
    df = sample.merge(preds, on="complaint_id")
    df = df[df["status"] == "ok"]
    expected = df["product"].map(PRODUCT_TO_CATEGORY)
    agrees = (df["category"] == expected) | (df["category"] == "fraud_scam")
    return [
        "## 3. Rough check on all complaints (category vs the consumer's chosen CFPB product)",
        f"- Agreement (fraud_scam always counted as agreeing): {pct(int(agrees.sum()), len(df))}",
        "- Not a true accuracy: consumers often pick the wrong product. Disagreements are worth reading.",
        "",
        "Predicted category distribution:",
        "",
        counts_table(df["category"], "category"),
        "",
    ]


def workload_section(preds):
    ok = preds[preds["status"] == "ok"]
    all_flags = [flag for flags in ok["guardrail_flags"] for flag in flags]
    return [
        "## 4. Human workload",
        f"- Sent to a human: {pct(int(preds['requires_human'].sum()), len(preds))}",
        f"- LLM alone would have sent: {pct(int(ok['llm_requires_human'].sum()), len(ok))}",
        "",
        "Guardrail flags raised:",
        "",
        counts_table(all_flags, "flag"),
        "",
    ]


def cost_section(preds):
    tokens_in = preds["input_tokens"].mean()
    tokens_out = preds["output_tokens"].mean()
    per_complaint = (tokens_in * PRICE_INPUT_PER_MILLION + tokens_out * PRICE_OUTPUT_PER_MILLION) / 1e6
    model = preds["model"].iloc[0]
    return [
        "## 5. Cost (measured token usage, retries included)",
        f"- Model: {model}; prices used: ${PRICE_INPUT_PER_MILLION}/M input, ${PRICE_OUTPUT_PER_MILLION}/M output tokens",
        f"- Average tokens per complaint: {tokens_in:.0f} in, {tokens_out:.0f} out",
        f"- Cost per complaint: ${per_complaint:.5f}",
        f"- Cost for {COMPLAINTS_PER_MONTH:,} complaints/month: ${per_complaint * COMPLAINTS_PER_MONTH:,.2f}",
        "",
    ]


def adversarial_section():
    if not ADVERSARIAL_FILE.exists():
        return ["## 6. Adversarial set", "Not run yet (see README).", ""]
    preds = read_jsonl(ADVERSARIAL_FILE)
    cases = pd.read_csv(ADVERSARIAL_INPUT).merge(preds, on="complaint_id")
    lines = [
        "## 6. Adversarial set (synthetic prompt-injection and edge cases)",
        "",
        "| id | attack | expected | predicted | urgency | human? | flags |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in cases.itertuples():
        lines.append(f"| {r.complaint_id} | {r.attack_type} | {r.expected_category} | {r.category} | "
                     f"{r.urgency} | {r.requires_human} | {', '.join(r.guardrail_flags)} |")
    passed = int(cases["requires_human"].sum())
    lines += ["", f"Sent to a human: {passed}/{len(cases)} (target: all). "
                  f"Category correct: {int((cases['category'] == cases['expected_category']).sum())}/{len(cases)}", ""]
    return lines


def write_summary_review_sheet(preds, sample, labels):
    """Summaries can't be scored automatically. This sheet puts each summary next to the text so a
    person can mark it faithful (yes/no) and note any invented detail."""
    df = labels[["complaint_id"]].merge(sample, on="complaint_id").merge(preds, on="complaint_id")
    df = df[["complaint_id", "narrative", "summary", "confidence_note"]].copy()
    df["summary_faithful_yes_no"] = ""
    df["invented_detail_yes_no"] = ""
    df.to_csv(SUMMARY_REVIEW_FILE, index=False)


def main():
    preds = read_jsonl(PREDICTIONS_FILE)
    labels = pd.read_csv(HAND_LABELS_FILE)
    sample = pd.read_csv(SAMPLE_FILE)

    report = ["# Part B evaluation results", ""]
    report += reliability_section(preds)
    report += hand_label_section(preds, labels)
    report += silver_section(preds, sample)
    report += workload_section(preds)
    report += cost_section(preds)
    report += adversarial_section()

    REPORT_FILE.write_text("\n".join(report), encoding="utf-8")
    write_summary_review_sheet(preds, sample, labels)
    print("\n".join(report))
    print(f"\nSaved {REPORT_FILE} and {SUMMARY_REVIEW_FILE}")


if __name__ == "__main__":
    main()
