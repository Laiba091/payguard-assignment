# Part B: LLM complaint triage (run in VS Code)

An LLM reads each customer complaint and returns a structured record:

| Field | Meaning |
|---|---|
| `category` | which team should handle it (one of 8) |
| `urgency` | low, medium or high |
| `summary` | one or two sentences |
| `requires_human` | true or false |
| `confidence_note` | when or why this triage might be wrong |

## Folder layout

```
part_b_complaint_triage/
├── make_sample.py      step 1: picks the 400 complaints (already done, output included)
├── triage.py           step 2: sends each complaint to the LLM, checks the answer, applies safety rules
├── evaluate.py         step 3: compares the results with the hand labels and calculates cost
├── test_triage.py      tests that use a fake LLM (no key or internet needed)
├── requirements.txt
├── .env.example        template for your API key
├── data/
│   ├── complaints_sample.csv        the 400 real CFPB complaints
│   ├── hand_labels.csv              60 complaints with the "correct" answers  ← YOU REVIEW THESE
│   ├── adversarial_complaints.csv   8 fake "attack" complaints (prompt injection etc.)
│   ├── label_sheet_blank.csv        the same 60 complaints with empty answers
│   ├── source/                      the original 10,000-complaint download
│   └── README.md                    where the data came from + labelling rules
└── results/            created when you run the scripts
```

## One-time setup

1. Unzip the folder. In VS Code, use **File → Open Folder** to open `part_b_complaint_triage`.
2. Open **Terminal → New Terminal** and run:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

3. Open the new **`.env`** file in VS Code and replace `your-key-here` with your Gemini API key. Get the key at https://aistudio.google.com → **Get API key**. Save the file. **Never upload `.env` to GitHub.**
4. Press **Ctrl+Shift+P**, choose **Python: Select Interpreter**, and pick the one that shows `.venv`.

## Run it (in this order)

| Step | Command | Time | What you should see |
|---|---|---|---|
| 1. Tests | `python -m pytest -q` | 2 s | `10 passed` |
| 2. Small test with the real LLM | `python triage.py --limit 5` | 30 s | 5 lines like `[1/5] 9961021: ok debt_collection / medium / human=False` |
| 3. All 400 complaints | `python triage.py` | about 30 min | one line per complaint |
| 4. Attack test | `python triage.py --input data/adversarial_complaints.csv --output results/part_b_adversarial.jsonl` | 1 min | 8 lines |
| 5. Evaluation | `python evaluate.py` | 2 s | the full results report |

Notes:
- **If step 3 stops** (internet drop, or you close the laptop), just run the same command again. It skips the complaints already done.
- **If step 2 fails, stop there** and send me the error before running step 3.

After step 5, open `results/part_b_evaluation.md` in VS Code. Press **Ctrl+Shift+V** to see it formatted. These are the numbers for your README.

## Things you can change easily

| What | Where |
|---|---|
| Which LLM to use | the `.env` file (`LLM_MODEL`, `LLM_BASE_URL`) |
| The 8 categories and their descriptions | `CATEGORIES` at the top of `triage.py` |
| Words that force human review (lawyer, fraud…) | `SENSITIVE_PATTERNS` in `triage.py` |
| Retries per complaint | `MAX_ATTEMPTS` in `triage.py` |
| Token prices used for the cost estimate | `PRICE_INPUT_PER_MILLION` and `PRICE_OUTPUT_PER_MILLION` in `evaluate.py` |

## Common problems

| Problem | Fix |
|---|---|
| `LLM_API_KEY is missing` | The `.env` file doesn't exist, or the key isn't saved in it |
| `429` or "rate limit" messages | That's the free-tier limit. The script waits and retries by itself; increase `LLM_SLEEP_SECONDS` in `.env` if it keeps happening |
| `404` / model not found | The model name changed. Put a current Flash-Lite model name in `LLM_MODEL` in `.env` |
| Many `failed` lines | Stop with Ctrl+C and send me the error text |
