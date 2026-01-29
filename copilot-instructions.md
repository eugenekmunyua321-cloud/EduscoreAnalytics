## Copilot / Agent Instructions — EduScore Analytics (Exam1)

Purpose: fast, actionable guidance so an AI coding agent can be immediately productive in this codebase.

Overview
- This is a Streamlit-based school exam management app. Primary entry points are `app.py` (original exam flow) and `home.py` (new dashboard). The app uses `st.session_state` extensively for navigation and persistence.
- Persistent data lives under `saved_exams_storage/` (per-school subfolders when signed in). Key files:
  - `saved_exams_storage/exams_metadata.json` — master index of saved exams
  - `saved_exams_storage/<exam_id>/data.pkl` and `raw_data.pkl` — pandas pickles of processed/raw data
  - `saved_exams_storage/<exam_id>/config.json` — exam config
  - `saved_exams_storage/student_photos/` and `student_photos.json` — photo storage and mappings

Key files and responsibilities
- `app.py` — main app loader, auth gate. Delegates to `home.py` after sign-in by reading and exec()-ing the file. Avoid changing delegation logic unless needed.
- `home.py` — recommended primary dashboard implementation (used post-login). Many flows navigate here.
- `pages/*.py` — page modules implementing UI features (e.g., `pages/student_history.py`, `pages/saved_exams.py`, `pages/report_cards.py`).
- `modules/` — helper modules (notably `modules/auth.py` and `modules/storage.py`). Use `modules.storage.get_storage_dir()` to get the correct per-school storage path.
- `utils/` — utility helpers (e.g., `utils/student_photos.py`) used for image handling.

Architecture & data flow (concise)
- User signs in via `modules.auth.get_current_school_id()`; if set, app uses a per-school subfolder under `saved_exams_storage/`.
- Saving an exam: `app.save_exam_to_disk()` updates `exams_metadata.json` and writes per-exam pickles and `config.json`.
- Loading: pages call `load_all_exams_from_disk()` or read per-exam `data.pkl` / `raw_data.pkl` via `modules.storage.get_storage_dir()`.
- UI navigation is controlled via `st.session_state` keys such as `current_page`, `view`, `go_to_analysis`, `selected_saved_exam_id`, and saved exam caches like `saved_exam_data`, `saved_exam_raw_data`, `saved_exam_configs`.

Project-specific conventions and gotchas
- Persistence: DataFrames are stored as pandas pickles (`.to_pickle` / `pd.read_pickle`) — keep that format when writing new persistence code.
- Defensive coding: many modules use broad try/except and fallback paths (e.g., fallback to global `saved_exams_storage/`). Tests/agent changes should be mindful — add targeted exception handling rather than removing fallbacks.
- Photo handling: images are resized and normalized; `student_photos.json` maps IDs to filenames. Student ID selection prefers Admission Number, else SHA1(name) (first 16 chars) — follow this when linking photos.
- PDF generation: uses ReportLab for tables and images. Tables use manual column width calculations — be conservative when changing layout logic.
- Session dependencies: many pages assume certain `st.session_state` keys exist (e.g., `cfg`, `saved_exams` lists). When editing or adding pages, either set defaults early or guard access with `.get()` checks.

Common tasks & examples (copy/paste friendly)
- Get storage dir (use this instead of hardcoding paths):
  from modules.storage import get_storage_dir
  storage_dir = get_storage_dir()

- Save exam example (follow `app.save_exam_to_disk` contract):
  - update `exams_metadata.json` (dictionary keyed by exam_id)
  - create `saved_exams_storage/<exam_id>/` and write `data.pkl`, `raw_data.pkl`, `config.json`

- Read exams metadata:
  import json, os
  meta_path = os.path.join(get_storage_dir(), 'exams_metadata.json')
  with open(meta_path,'r',encoding='utf-8') as f: meta = json.load(f)

How to run & debug locally
- Create a Python environment and install requirements from `requirements.txt` (project expects Streamlit, pandas, ReportLab, Pillow, openpyxl, etc.).
- Start the app (recommended flows):
  - Dashboard: `streamlit run home.py`
  - Direct exam flow: `streamlit run app.py` (app.py will redirect to `home.py` when signed-in)
- For interactive debugging add `st.write()` or inspect `st.session_state` keys. Many pages expose debug info in `st.session_state.debug_loaded_info`.

Integration points & external dependencies
- Auth: `modules/auth.py` — used to determine per-school storage. Changing auth behavior affects storage and multi-account separation.
- Storage: `modules/storage.py` centralizes per-school storage path. Prefer this helper for file IO.
- External libs: Streamlit (UI), pandas (dataframes/pickles), ReportLab (PDF), Pillow (image processing), openpyxl (Excel), plotly optional for charts.

Testing hints
- There are no formal tests in the repo. When adding tests, mock `modules.storage.get_storage_dir()` and `modules.auth.get_current_school_id()` to isolate filesystem and auth.
- Use temporary directories and create small sample `data.pkl` and `exams_metadata.json` when unit testing pages.

If you edit UI flows
- Prefer editing `home.py` or files under `pages/` rather than modifying `app.py` delegation behavior. `app.py` contains logic that exec()-loads `home.py` to preserve old behaviour.

If anything is unclear or you want the instructions to include more examples (e.g., exact `st.session_state` keys, or an example of saving/loading an exam), tell me which area to expand and I will update this file.
