# Part A: Fraud detection (run in VS Code)

## Folder layout

```
part_a_fraud_detection/
├── fraud.py            ← the whole Part A code (one file)
├── requirements.txt    ← Python libraries needed
├── README.md           ← this file
├── data/
│   └── creditcard.csv  ← YOU put the dataset here
└── results/            ← created automatically when you run the code
```

## One-time setup

1. **Install Python** (3.10 or newer) from python.org. During install, tick **"Add Python to PATH"**.
2. **Install VS Code**, then install the **Python** extension (by Microsoft) from the Extensions tab.
3. **Download the dataset** from https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud (free account). Unzip it and put `creditcard.csv` inside the `data` folder.
4. In VS Code, go to **File → Open Folder** and choose the `part_a_fraud_detection` folder.
5. Open the terminal with **Terminal → New Terminal** and run these lines one by one:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Mac or Linux, the second line is `source .venv/bin/activate` instead.

6. Press **Ctrl+Shift+P**, choose **Python: Select Interpreter**, and pick the one that shows `.venv`.

## Run it

Open `fraud.py` and click the **▶ Run** button in the top-right corner. You can also type this in the terminal:

```
python fraud.py
```

It takes about 30 seconds. The end of the output should look like this:

```
gradient_boosting: PR-AUC 0.805 (95% CI 0.722-0.882), ROC-AUC 0.981
   at threshold 0.0326: precision 0.75, recall 0.76, TP 56, FP 19, FN 18
   cost $2,501 vs $7,728 with no model, ...
```

Three files appear in the `results` folder:

| File | What it shows |
|---|---|
| `part_a_metrics.json` | all the numbers |
| `part_a_pr_curve.png` | how well each model separates fraud from normal payments |
| `part_a_cost_vs_threshold.png` | how the alert threshold was chosen |

## Things you can change easily

These settings are at the top of `fraud.py`, in the **SETTINGS** block:

| Setting | Meaning | Try |
|---|---|---|
| `REVIEW_COST` | cost of one false alarm, in $ | change 5.0 to 20.0: fewer alerts, more fraud missed |
| `TRAIN_SHARE`, `VALID_SHARE` | how the data is split by time | 0.70 / 0.15 |
| `N_BOOTSTRAP` | how many resamples are used for confidence intervals | 200 runs faster |

## Common problems

| Problem | Fix |
|---|---|
| `python` is not recognised | Reinstall Python and tick "Add to PATH", or type `py` instead of `python` |
| `Data file not found` | `creditcard.csv` is not in the `data` folder, or the name is different |
| `.venv\Scripts\activate` cannot be loaded (PowerShell) | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again |
| `No module named sklearn` | The `.venv` interpreter is not selected; repeat step 6 |
