# AI Inventory

A dark, read-only validation workspace for the AI Governance Team. Upload a Forms disclosure or raw agent export, inspect per-record findings, filter by field or value, and download reports. Built with Flask, HTML, CSS, JavaScript, and SQLite. No frontend build step or external services.

## Run

The project files are available directly in [nikhila-gregforge/Invent_test](https://github.com/nikhila-gregforge/Invent_test). Choose **Code → Download ZIP**, extract it, and open a terminal in the folder containing `app.py` and `requirements.txt`. You can rename that folder to `centen_project`.

If Git is available, you can instead run `git clone https://github.com/nikhila-gregforge/Invent_test.git centen_project` and then `cd centen_project`.

Use your existing Python and pip installation (tested with Python 3.12):

```bash
python -m pip install -r requirements.txt
python app.py
```

The same commands work in Windows PowerShell, macOS, and Linux. `requirements.txt` contains everything needed to run the app and the standard acceptance tests. SQLite is included with Python.

Open **http://127.0.0.1:8501**. The startup command uses Waitress and binds to localhost. Stop with Ctrl+C. To change the port: `PORT=8502 python app.py` on macOS/Linux, or set `$env:PORT = '8502'` in PowerShell.

## Test the experience

1. Choose **Upload file**, select the bundled **example.csv**, and click **Validate file**. Expect **3 total, 1 passed, 0 needs review, 2 failed**.
2. The table starts with the two failed records. Click **LLM Count** in the chart: only record `002` remains.
3. Click anywhere on that record's row. A separate record view opens with affected fields first: errors in red, warnings in amber, and each submitted value beside its validation message and expected condition. Use the field buttons to jump to an issue. **Back to results** returns to the same filters and page. Browser Back/Forward and refreshing a record URL also work. The view contains no editing controls.
4. Return to results and download **Issues for matching records**. The CSV contains findings for record `002` only.
5. Click **Clear filters** to see all three records. Explore **Fields**, **Rules**, search, severity, and column-value filters. Reload to verify the selected run and filters persist in the browser session.
6. Correct the source outside the app: change record `002`'s LLM count from `0` to `2`, and record `003`'s State from `None` to `California`. Upload the revised file. Expect **3 passed** in a new run; the earlier run remains unchanged.
7. Restart the application. Both runs remain in validation history.

The example is synthetic and uses 2026 dates. Test fixtures use explicit validation dates.

## Inputs and rules

- CSV and XLSX, up to **10 MiB / 10,000 data rows**. CSV uses UTF-8/BOM with Windows-1252 fallback. Multiple nonempty worksheets prompt for a selection. Formula cells in mapped XLSX fields are flagged; formulas are never evaluated.
- **Forms profile:** the original response ID and Q1–Q23 disclosure headers are required. Exact supported headers and aliases are in `inventory/__init__.py`.
- **Agent profile:** recognizes the reference export's `Title ID`, `Name`, and `Description` headers. Other expected source fields are checked individually; absent required values fail, while unavailable semantic mappings require review. Supported raw/optional headers are in `AGENT_HEADERS` and `AGENT_OPTIONAL`.
- Original cells, source row numbers, and file bytes are preserved. Extra columns appear in Fields, column-value filters, and reports as metadata with no configured validation rule.
- Each record has its own result. An error in one row never blocks unrelated rows or the entire column. Duplicate ID/application-ID checks flag the matching rows; repeated names produce warnings.
- **Passed:** all applicable configured checks passed. **Needs review:** no errors, but warnings or unresolved metadata remain. **Failed:** at least one error. These three whole-file totals are mutually exclusive.
- Test-only/placeholder names and purposes fail, including `test`, `test123`, `testing`, `this is a test`, `New Agent 4`, and `TBD`. Legitimate purposes such as “Automates regression testing for claims applications” remain valid. The rules are deterministic; they do not assess every possible vague or misleading description.
- Dropdowns require configured categories; Other requires details. Unknown risk, impact, or oversight requires review. Forms owner emails receive syntax checks; raw Owner/Publisher values receive meaningful-value checks, without claiming they establish inventory business/technical ownership.
- Model counts distinguish blank, zero, and Unknown. Whole-number representations such as `1.0` are accepted; mode names, negative numbers, fractions, and prose fail. Explicit LLM or ML/DL declarations require corresponding positive counts.
- Active systems need a valid nonfuture go-live date. Source creation/modification timestamps are checked for validity and ordering. Creation date is never substituted for go-live date; Available is never silently mapped to Active.
- Organization details do not infer business purpose, function, usage LOB, or geography. Missing acquisition type, usage LOB, or go-live metadata in agent exports requires review. Exactly 8,000 instruction characters flags possible truncation, not a confirmed error.
- **Rules** shows the stored rule descriptions for each run. Rule definitions and severity defaults live in `inventory/__init__.py` and `inventory/validation.py`.

## Filtering and reports

The totals at the top always describe the whole file. The matching-record count, chart, field statistics, table, and filtered reports use the same server-side query.

Status/search/column filters combine with AND. An affected-field, rule, and severity combination must match the **same finding**. Column-value filters inspect original submitted values; common-value buttons use exact matching. Blank means an empty cell, not zero, Unknown, or N/A. Charts count distinct affected records; field error/warning counts can overlap.

The table sorts and paginates on the server. A run may contain 10,000 records, but the browser receives at most 100 table rows per page.

The download menu provides:

- **Issues for matching records:** every finding for the matching records, including findings in other fields. One row per finding, with source locator, original values, rule, severity, and expected condition.
- **Matching records:** one row per matching record, with status/counts and original source columns.
- **Field summary for matching records:** completeness and distinct/affected/error/warning counts, plus rule descriptions.
- **All issues / All records in this file:** explicitly ignore active filters.

All reports are CSV with UTF-8 BOM. Formula-like values and headers are escaped for spreadsheet safety. Stored source values are unchanged. Every report identifies its validation run, rules version, and as-of date. An empty selection still produces a header-only record/issue report.

## Persistence and administration

Validation history is stored in **data/validations.sqlite3**: original uploads, compressed immutable results, source profile, file hash, validation date, and rule version. Identical content/worksheet/rule version/as-of date reopens the existing run. Changed content, rule version, or date produces a new run. Historical results never silently revalidate under new rules.

An existing **data/inventory.sqlite3** from the former onboarding application is preserved and not modified or displayed by this version. This application provides no editing, publishing, or inventory-write endpoints. To back up, stop the app and copy `data/`.

Optional environment variables:

| Variable | Default |
| --- | --- |
| `PORT` | `8501` |
| `AI_INVENTORY_DATA_DIR` | `./data` |
| `AI_INVENTORY_MAX_BYTES` | `10485760` |
| `AI_INVENTORY_MAX_ROWS` | `10000` |
| `AI_INVENTORY_HOSTS` | `localhost,127.0.0.1,[::1]` |

There is **no built-in login or SSO**. The supplied startup binds to localhost. Shared admin deployment requires an authenticated company hosting layer and explicit allowed host configuration. Merely setting allowed hosts does not authenticate users. No user-management module is included.

## Tests and results

```bash
python -m pytest -q -s
```

The current suite covers parsing/encodings, worksheet selection, limits, literal/formula preservation, per-record rules, placeholder false positives, duplicate diagnostics, immutable history, concurrent identical uploads, filters, exports, API error handling, pagination, and absence of mutation endpoints. The obsolete Streamlit editor/commit tests have been replaced by tests of the new workflow; parser and applicable rule coverage remain.

**103 tests passed**, including the browser regression and private agent-export check. The default shareable-package suite runs **101 passed, 2 skipped**: the browser test is opt-in and private company data is excluded. To run the optional reference test locally:

```bash
AI_INVENTORY_AGENT_SNAPSHOT=/path/to/sample.csv python -m pytest -q
```

To run the browser regression with installed Google Chrome (optional development dependency):

```bash
python -m pip install playwright
AI_INVENTORY_BROWSER_TESTS=1 AI_INVENTORY_BROWSER_CHANNEL=chrome python -m pytest -q
```

On PowerShell, set `$env:AI_INVENTORY_BROWSER_TESTS = '1'` and `$env:AI_INVENTORY_BROWSER_CHANNEL = 'chrome'` before running pytest. Alternatively, run `python -m playwright install chromium` and omit `AI_INVENTORY_BROWSER_CHANNEL`. The browser test starts an isolated server with synthetic data; it does not use your saved validation history.

The browser regression covers all six table cells, read-only error and warning highlighting, original and blank values, keyboard opening, field jumps, filtered pagination on return, browser Back/Forward, refresh and direct record URLs, failed-request retry, invalid record URLs, passed records, HTML escaping, and mobile overflow.

The 249-record private reference check verifies 5 test-only descriptions, 249 nonnumeric LLM counts, and 13 instruction-length flags. It does not copy that data into the distributable.

On Python 3.12.7/macOS, parsing plus validation took approximately **0.14 seconds for 1,000 records** and **1.32 seconds for 10,000 records**, using distinct synthetic owner emails. These measurements exclude persistence and browser rendering.

Chrome/Playwright checks passed upload, summary counts, chart-linked filters, read-only record details, CSV download, refresh persistence, Fields/Rules views, search/reset, and a 390-pixel mobile layout without page overflow or browser errors.

Additional browser checks passed schema-error handling, XLSX worksheet selection, the raw agent profile, pagination, literal HTML/XSS safety, exact common-value and column-value filters, matching/full-file exports, corrected re-upload, and preservation of the previous run.

## Shareable files

```text
app.py                  Flask routes and local startup
assets/
  index.html            Workspace and read-only record view
  style.css             Dark, responsive interface
  app.js                Filters, charts, navigation, upload, downloads
  centene-logo.jpg       Official bundled logo
inventory/
  __init__.py           Source contracts, options, rule descriptions
  ingestion.py          CSV/XLSX parsing
  normalization.py      Literal normalization
  validation.py         Per-record rules and batch duplicate flags
  storage.py            Immutable SQLite validation history
  exports.py            Shared filtering, field analysis, CSV reports
tests/
  test_inventory.py     Parser, rule, storage, and reporting tests
  test_app.py           HTTP and optional browser acceptance tests
example.csv             Three synthetic records
requirements.txt        Python dependencies
README.md               Setup, operation, validation, limitations
.gitignore              Local data and generated-file exclusions
```

**17 files**. The repository contains the source, tests, setup instructions, and synthetic example. Local databases, uploaded company data, virtual environments, caches, and original handoff documents are excluded. The app loads no remote assets or fonts and sends no data to external services.

The unchanged [Centene logo](https://www.centene.com/content/dam/centenedotcom/logos/centene_logo_2023.jpg) is bundled locally. Blue/teal accents retain the earlier corporate treatment; the dark surfaces and layout are designed for this review workflow.
