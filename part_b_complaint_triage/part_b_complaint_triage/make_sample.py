"""
Part B, step 1 - build the reproducible complaint slice.
Source: official CFPB narratives archive (FOIA Electronic Reading Room), file CCDB_Export_20_July_2026
https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/
Put the ONE archive file (.zip or the unzipped .csv) in data/source/, then run:  python make_sample.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCE_FOLDER = ROOT / "data" / "source"
OUTPUT_FILE = ROOT / "data" / "complaints_sample.csv"
LABEL_SHEET_FILE = ROOT / "data" / "label_sheet_blank.csv"

DATE_FROM = "2026-07-01"   # first day included
DATE_TO = "2026-07-07"     # last day included
SAMPLE_SIZE = 400
PER_PRODUCT = 35
MIN_CHARS = 200
MAX_CHARS = 5000
RANDOM_SEED = 42
N_TO_HAND_LABEL = 60

COLUMNS = {
    "Complaint ID": "complaint_id",
    "Date received": "date_received",
    "Product": "product",
    "Consumer complaint narrative": "narrative",
}


def find_source_file():
    files = [f for f in SOURCE_FOLDER.glob("*") if f.suffix.lower() in (".csv", ".zip")]
    if len(files) != 1:
        raise SystemExit(f"Put exactly ONE .csv or .zip file in {SOURCE_FOLDER}. Found: {[f.name for f in files]}")
    print(f"Using source file: {files[0].name}")
    return files[0]


def load_source():
    source_file = find_source_file()
    header = pd.read_csv(source_file, nrows=0)
    missing = [c for c in COLUMNS if c not in header.columns]
    if missing:
        raise SystemExit(f"Columns {missing} not found. The file has: {list(header.columns)}")
    kept = []
    total = 0
    for chunk in pd.read_csv(source_file, usecols=list(COLUMNS), chunksize=200_000, dtype=str):
        total += len(chunk)
        chunk = chunk.rename(columns=COLUMNS)
        day = pd.to_datetime(chunk["date_received"], format="mixed", errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
        has_text = chunk["narrative"].fillna("").str.strip() != ""
        kept.append(chunk[(day >= DATE_FROM) & (day <= DATE_TO) & has_text])
    df = pd.concat(kept)
    df["complaint_id"] = df["complaint_id"].astype(int)
    print(f"Rows in source file: {total:,}")
    print(f"Received {DATE_FROM} to {DATE_TO} with a narrative: {len(df):,}")
    return df


def main():
    df = load_source()
    length = df["narrative"].str.len()
    df = df[(length >= MIN_CHARS) & (length <= MAX_CHARS)]
    print(f"After length filter {MIN_CHARS}-{MAX_CHARS} chars: {len(df):,}")
    df = df.drop_duplicates(subset="narrative")
    print(f"After removing duplicate narratives: {len(df):,}")

    df = df.sort_values("complaint_id").reset_index(drop=True)
    picks = []
    for product, group in df.groupby("product"):
        picks.append(group.sample(n=min(len(group), PER_PRODUCT), random_state=RANDOM_SEED))
    per_product = pd.concat(picks)
    rest = df.drop(per_product.index)
    fill = rest.sample(n=max(SAMPLE_SIZE - len(per_product), 0), random_state=RANDOM_SEED)
    sample = pd.concat([per_product, fill]).sort_values("complaint_id")

    sample[["complaint_id", "date_received", "product", "narrative"]].to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(sample)} complaints to {OUTPUT_FILE}")
    print(sample["product"].value_counts().to_string())

    sheet = sample.sample(n=N_TO_HAND_LABEL, random_state=RANDOM_SEED).sort_values("complaint_id")
    sheet = sheet[["complaint_id", "product", "narrative"]].copy()
    for column in ["category", "alt_category", "urgency", "requires_human", "label_note"]:
        sheet[column] = ""
    sheet.to_csv(LABEL_SHEET_FILE, index=False)
    print(f"Saved blank hand-label sheet ({N_TO_HAND_LABEL} rows) to {LABEL_SHEET_FILE}")


if __name__ == "__main__":
    main()
