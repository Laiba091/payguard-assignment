# Data (Part B)

## Source: official CFPB narratives archive

**The live CFPB database no longer has narratives.** The CFPB stopped publishing complaint narratives on its live Consumer Complaint Database on **14 August 2026**. Its website search, CSV export and API now return only structured fields (product, issue, company…), with no customer text. We confirmed this: a CSV export for 1–8 Sept 2024 with `has_narrative=true` returned 64,043 rows and **no narrative column**.

The CFPB moved all previously published narratives to an official archive in its FOIA Electronic Reading Room:
https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/

**File used:** `CCDB_Export_20_July_2026.zip`, which contains `CCDB_Export_20_July_2026.csv`.
Download link: https://files.consumerfinance.gov/f/documents/CCDB_Export_20_July_2026.zip

| Check | Value |
|---|---|
| Rows in `CCDB_Export_20_July_2026.csv` | 672,036 |
| MD5 of that CSV | `7B3AA760413E5A6D4C73DC2E7A1FD7A9` |
| Downloaded | 16 October 2026 |

The raw CSV (216 MB) is **not committed**, because it is over GitHub's 100 MB file limit. To reproduce: download the ZIP, unzip it, put the CSV in `data/source/`, and run `python make_sample.py`.

## Files in this folder

| File | What it is |
|---|---|
| `complaints_sample.csv` | The 400-complaint slice used in Part B. MD5 `1EB6C68287B941630FCD91475083F337`. |
| `label_sheet_blank.csv` | 60 complaints picked at random from the slice for hand labelling. |
| `hand_labels.csv` | The filled-in labels; the "answer key" used by `evaluate.py`. |
| `adversarial_complaints.csv` | 8 **synthetic** complaints that test prompt injection and edge cases. They are clearly not real data. |

## Exact selection criteria

These are applied by `make_sample.py`. Running it again on the same CSV gives the same 400 complaints (same MD5).

| Step | Rule | Complaints left |
|---|---|---|
| 0 | All rows in the July 2026 archive file | 672,036 |
| 1 | Received **1–7 July 2026** (inclusive) **and** has a non-empty narrative | 4,350 |
| 2 | Narrative length 200–5,000 characters | 3,964 |
| 3 | Remove duplicate narrative text (copy-paste template letters) | 3,706 |
| 4 | Sort by Complaint ID; for each of the 11 CFPB products take up to 35 at random (seed 42); fill to 400 at random from the rest (seed 42) | **400** |

Notes on these rules:
- Very short narratives are dropped because they rarely contain enough information to triage.
- The 5,000-character cap keeps the cost predictable.
- Step 4 balances products on purpose, so that every routing queue gets tested. As a result, the metrics describe this balanced slice and are **not** weighted to match the real mix of complaints.

CFPB narratives are published only with the consumer's consent, and personal details are removed by the CFPB; these show as `XXXX`.

## Labelling guide (used for `hand_labels.csv`)

**category**: the queue that should own the complaint. The definitions are in `CATEGORIES` in `triage.py`.
- Identity theft that shows up on a credit report counts as `credit_reporting`.
- Unauthorized transactions, scams and accounts opened by someone else count as `fraud_scam`.

**alt_category**: filled in only when a second queue would also be a reasonable owner. Evaluation reports both a strict score (category only) and a lenient score (category or alt_category).

**urgency**:
- high: money missing or frozen right now, active fraud, an imminent foreclosure, repossession or eviction, a legal threat, or a vulnerable person at risk.
- medium: a concrete problem that is not time-critical.
- low: service quality, a question, or an issue that is already resolved.

**requires_human**: `true` if any of the following apply:
- a fraud, scam or identity-theft allegation
- an explicit legal threat or legal claim (lawyer, lawsuit, suing, statutory or punitive damages)
- high urgency
- a vulnerable customer (bereavement, elderly, hardship, distress)
- harassment
- mixed issues that need judgement

Quoting a statute without a threat does not count as a legal claim.

**label_note**: one line on why.
