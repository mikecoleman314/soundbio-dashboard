# Local Development Guide

## Requirements

- Python 3.14 (installed via Homebrew: `/opt/homebrew/bin/python3.14`)
- `service_account.json` in the repo root (get from the person who set up the Google Cloud project — do not commit this file)
- The `.venv` must be built from the current folder path (see setup below)

---

## One-time setup

Run this from the repo root after cloning or after moving the folder:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> **Why:** The venv embeds the path it was created at. If the folder moves, the venv breaks and must be rebuilt. Always use `.venv/bin/streamlit`, never the system `streamlit`.

---

## Running the apps locally

**Main dashboard (`app.py`):**
```bash
.venv/bin/streamlit run app.py
```
Opens at `http://localhost:8501`

**Standalone volunteer signup (`volunteer_app.py`):**
```bash
.venv/bin/streamlit run volunteer_app.py
```
Opens at `http://localhost:8501` (or `8502` if the dashboard is already running)

Both apps read from live Google Sheets using `service_account.json`. 

**There is no local mock** — edits you test locally affect the real sheets. Plan your edits carefully, create backups if you are unsure.

---

## Workflow for local edits

1. Edit `app.py` or `volunteer_app.py` in any editor. I like vscode for major edits and BBedit for small ones, this choice is personal preference.
2. Streamlit hot-reloads on save — no restart needed for most changes
3. If the app gets into a bad state, click **Rerun** in the browser or restart the process
4. When satisfied, commit and push — Streamlit Cloud redeploys automatically

---

## Shared code note

`volunteer_app.py` contains a self-contained copy of the volunteer functions. If you change signup/cancellation logic, update it in **both** `app.py` and `volunteer_app.py`.

---

## What NOT to commit

- `service_account.json` — contains private credentials
- `.venv/` — already in `.gitignore`
- `.DS_Store`
