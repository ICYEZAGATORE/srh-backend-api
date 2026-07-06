# SRH LLM Benchmark — Colab Handoff / Context Summary

## Purpose
Bilingual (English/Kinyarwanda) SRH (Sexual & Reproductive Health) conversational-agent
LLM benchmark. Notebook: `notebooks/llm_benchmark.ipynb`. Designed to run on **Google Colab
with a GPU** (local runs show `GPU: NONE`).

## What we set out to fix
1. A cell appeared to "hang" — diagnosed as **blocking on input** (`getpass()` for the HF
   token, then the `files.upload()` widget), not slow compute.
2. The eval-set load cell had a **hardcoded Windows path**
   (`C:\Users\USER\srh-backend-api\evaluation\srh_eval_set.json`) that can't exist in Colab.
3. Make eval-set loading portable across the three Colab provisioning paths:
   git clone, `files.upload()` widget, and file-browser upload to `/content/`.

## Key Colab facts learned
- `files.upload()` widgets only work **during live execution in the current browser
  session**; a re-opened/stale saved widget is inert ("Upload widget is only available
  when the cell has been executed in the current browser session").
- File-browser uploads land in **`/content/`**.
- A **runtime reset wipes `/content/`**.
- The clone cell does `%cd srh-backend-api`, so cwd becomes `/content/srh-backend-api`
  while the file browser drops files in `/content/` — hence absolute `/content/` paths
  were added to the loader candidates.
- Colab does **not** auto-sync local/VSCode notebook edits — Colab must open the pushed
  GitHub version to get fixes.
- `Import "google.colab" could not be resolved (Pylance/reportMissingImports)` is a
  **harmless local static-analysis warning** — `google.colab` exists only in the Colab
  runtime, not locally. No effect on Colab execution. Silence with `# type: ignore` if desired.

## Current load cell (committed)
```python
# Load the eval set. Prefer EVAL_PATH from the upload cell; otherwise search the
# common Colab locations.
_candidates = []
try:
    _candidates.append(EVAL_PATH)                       # set by the upload cell
except NameError:
    pass
_candidates += [
    Path('srh_eval_set.json'),                          # current working dir
    Path('/content/srh_eval_set.json'),                 # Colab file-browser upload
    Path('evaluation/srh_eval_set.json'),               # cloned repo (cwd)
    Path('/content/srh-backend-api/evaluation/srh_eval_set.json'),
]
EVAL_PATH = next((p for p in _candidates if p and p.exists()), None)
if EVAL_PATH is None:
    raise FileNotFoundError(
        'srh_eval_set.json not found. Upload it (file browser drops it in /content/) '
        'or run the upload cell above. Searched: '
        + ', '.join(str(p) for p in _candidates if p))

data = json.loads(EVAL_PATH.read_text(encoding='utf-8'))
QUESTIONS = data['questions']
QBYID = {q['id']: q for q in QUESTIONS}
print(f"Loaded {len(QUESTIONS)} questions from {EVAL_PATH}; topics:",
      sorted({q['topic'] for q in QUESTIONS}))
```

## Upload cell (Colab-only)
```python
from google.colab import files  # type: ignore
uploaded = files.upload()
EVAL_PATH = Path(next(iter(uploaded)))
print('Uploaded', EVAL_PATH.name, '·', EVAL_PATH.stat().st_size, 'bytes')
```

## Git / deployment state
- `evaluation/srh_eval_set.json` (30,542 bytes, 30 questions) committed (`fb9c711`) and pushed.
- Fixed notebook committed (`c3000ec`) and pushed to `origin/main`.
- Open the correct version directly in Colab:
  `https://colab.research.google.com/github/ICYEZAGATORE/srh-backend-api/blob/main/notebooks/llm_benchmark.ipynb`

## Open items / next steps
- Confirm the load cell runs in Colab (expect `Loaded 30 questions ...`).
- If still FileNotFound: likely Colab ran a **stale notebook copy** and/or `/content` was
  **wiped on a runtime reset** — re-open from the GitHub link above and re-upload after reset.
- To continue troubleshooting locally after a full Colab run, bring back: the executed
  notebook (with outputs) and any generated results/artifacts (e.g. benchmark scores JSON/CSV).

## Note on the eval set
Its reference answers **require clinical review** before being treated as authoritative and
are **not ingested** into the knowledge base.
