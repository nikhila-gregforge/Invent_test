# AI Inventory · AI Governance Team

A dark, read-only workspace for batch inventory validation. Admins upload a file, confirm how its columns map to inventory fields, review individual records, and download reports. Built with Flask, HTML/CSS/JavaScript and SQLite; no frontend build or external service is required.

## Setup

Download the project using **Code → Download ZIP** in [Invent_test](https://github.com/nikhila-gregforge/Invent_test), then extract it. Open a terminal in the folder containing `app.py` and `requirements.txt`. You can name the extracted folder `centen_project`.

Alternatively:

```bash
git clone https://github.com/nikhila-gregforge/Invent_test.git centen_project
cd centen_project
```

Use Python **3.10 or newer** and pip (tested on Python 3.12.7):

```bash
python -m pip install -r requirements.txt
python app.py
```

These commands work in Windows PowerShell, macOS and Linux. On systems that name Python `python3`, substitute that command. SQLite is included with Python. No virtual environment or additional package manager is required.

Open **http://127.0.0.1:8501**. Stop with Ctrl+C. Waitress serves the app on localhost.

## Test the experience

1. Choose **Upload file**, select `example.csv`, then **Continue to mapping**. No review is saved at this point.
2. Review the suggested source columns and sample values. Open **Rules** beside a field to see its requirements, severity explanations and accepted values. Click **Confirm mapping & validate**.
3. Expect **3 records: 2 with errors, 0 with warnings only, 1 passed**. The table initially shows records needing attention. No matching-record dashboard or field-analysis sections appear on the first page.
4. Select **LLM Count** under **Issues in field**. Only record `002` remains. Click any cell in its row. A separate, read-only record view highlights the technology/count inconsistency and explains why it is an error. The submitted count is `0`.
5. Use **Back to results**. The filter and page are retained. Open **Download report**, keep **Current view**, and download the **Issues report**. It contains issues for record `002`. Select **Entire file** to export all records instead.
6. Correct the source file externally: change record `002`'s LLM count to `2`, and record `003`'s State from `None` to `California`. Upload it again, review the remembered mapping, and validate. Expect **3 passed** in a new review. The earlier review remains unchanged.
7. Try a file with different headers. Map each inventory field to the relevant source column, or choose **Not provided**. Renaming a column does not change validation policy. Business and technical owners accept a named person or one valid email.
8. Restart the app and open **Reviews**. Saved reviews and their original findings remain available. Record URLs support refresh and browser Back/Forward.

The example is synthetic and uses 2026 dates. Automated fixtures use an explicit validation date.

## Mapping and validation

The inventory contract contains **23 fields plus an optional source record ID**. The filename and export format never choose a different rule set.

- **CSV/XLSX:** up to 10 MiB and 10,000 data rows. UTF-8/BOM and Windows-1252 CSV are supported. Select a worksheet when an XLSX contains several nonempty sheets. Blank or duplicate headers must be corrected externally.
- **Suggestions need confirmation:** recognized headers are hints, not a hardcoded import mapping. Ambiguous matches remain unresolved. Publisher, Owner, creation timestamps and organizational LOB are not automatically assigned to accountable owners, go-live dates or usage LOB.
- **Explicit decisions:** choose one source column or Not provided for every inventory field. A source column can supply only one inventory field. Required fields may be marked Not provided; the review then shows a file notice and a missing-field error on every record. Conditional fields follow their displayed rules.
- **Remembered mappings:** the most recently confirmed choices are suggested for the same normalized header set and rules version, regardless of filename, column order, capitalization or surrounding spacing. Every upload still requires confirmation. Changed headers start a new mapping review.
- **Original values:** source rows, columns, cells, original upload bytes and the confirmed mapping are retained. Unmapped columns are reference data; they do not produce inventory findings. XLSX formulas in mapped fields produce errors and are never evaluated.
- **Independent records:** errors affect the relevant record. Duplicate source/application IDs flag the matching rows; repeated names produce warnings. Numeric identifiers and leading zeros are preserved.
- **Statuses:** Errors means at least one error; Warnings means no errors but one or more warnings or incomplete checks; Passed means all applicable checks completed without findings. The file totals count records and are mutually exclusive. A cross-field finding is one issue even when both fields are highlighted.
- **Dependencies:** a check blocked by a missing/invalid prerequisite appears under **Checks could not run**. It is never presented as a passed check.

The **View validation rules** dialog is available during mapping, results and record review. Each field shows its format, examples, accepted choices, requirements, Error/Warning severity, reason and source correction action. The same catalogue in `inventory/validation.py` drives validation, UI explanations and issue reports. Saved reviews retain their original rules and explanations.

Examples of applied rules:

- Real names and purposes are required. Test-only text such as `test`, `test123`, `this is a test`, `New Agent 4` and `TBD` fails. A meaningful description such as “Automates regression testing for claims applications” is accepted.
- Business and technical owners accept a meaningful name, optionally with role/department, or one syntactically valid email. Invalid email formats fail. Valid addresses outside `centene.com` receive a warning asking for confirmation.
- Counts distinguish blank, zero and Unknown. Model names, response modes, negatives and fractions fail. Declared LLM or ML/DL use requires a positive corresponding count. Broad technology labels may need confirmation rather than an assumed count.
- Choice fields use the listed inventory values and documented aliases. Multiple choices use semicolons; Other requires a description. Allowed Unknown classifications receive warnings.
- Active systems require a valid, nonfuture go-live date. Submission dates cannot be future. Supported formats are `YYYY-MM-DD`, US month/day slash dates and Excel date cells.
- Vendor acquisition requires a meaningful vendor contact. Medicaid usage requires a jurisdiction. Exclusive choices such as None and All States cannot be combined with other selections.

## Review and reports

The first page contains upload access and recent reviews. Results contain only file totals, search, status/issue-field filters, a paginated record table, rules and downloads. Search covers name, source ID, application ID and business owner. **Issues in field** selects records with a finding involving that inventory field.

The two CSV reports use the same record selection as the table:

- **Issues report:** every finding on the selected records, including source row, inventory fields, mapped source columns, submitted values, requirement, severity reason and source correction action.
- **Records report:** one row per selected record, status/counts, incomplete checks, confirmed mapping and every original source value. Source headers use the prefix `Source: ` to prevent collisions with report columns such as Errors or Record ID.

**Current view** includes all filtered records across pages. **Entire file** ignores filters. Both reports include the run ID, original filename, worksheet, rules version, validation date and mapping fingerprint. Empty selections produce a header-only CSV. Formula-like CSV values are prefixed with an apostrophe for spreadsheet safety; the database retains the original input.

## Persistence and operations

`data/validations.sqlite3` stores original uploads, immutable result snapshots and confirmed mapping choices. Identical file bytes, worksheet, mapping, rules version and validation date reopen the same review. A changed mapping creates a separate review even for identical file bytes.

On first startup with a version-2 history database, the app saves `data/validations-before-mapping.sqlite3` and migrates the history schema. Old snapshots and uploaded bytes are not rewritten or revalidated. Historical reviews show the rule information captured at that time; they do not gain newly introduced explanations. The old onboarding `data/inventory.sqlite3` is left untouched. To back up, stop the application and copy `data/`.

Expected upload errors appear in the UI. Unexpected server failures return a generic error and log the exception type in the terminal without logging submitted values. There is no persistent failure-log dashboard or background reprocessing.

| Environment variable | Default |
| --- | --- |
| `PORT` | `8501` |
| `AI_INVENTORY_DATA_DIR` | `./data` |
| `AI_INVENTORY_MAX_BYTES` | `10485760` |
| `AI_INVENTORY_MAX_ROWS` | `10000` |
| `AI_INVENTORY_HOSTS` | `localhost,127.0.0.1,[::1]` |

For a different port, use `PORT=8502 python app.py` on macOS/Linux, or `$env:PORT = '8502'` followed by `python app.py` in PowerShell.

## Acceptance tests

```bash
python -m pytest -q -s
```

**110 passed, 4 skipped** in the default shareable suite. The skips are three opt-in browser tests and one private reference check. **114 passed** with both enabled. Checks cover mapping integrity/reuse, arbitrary headers, owners, dependencies, record independence, parsing, duplicate IDs, migration, concurrent uploads, immutable history, filters, report provenance, safe exports, API errors and read-only endpoints.

Optional browser tests use installed Google Chrome and Playwright:

```bash
python -m pip install playwright
```

macOS/Linux:

```bash
AI_INVENTORY_BROWSER_TESTS=1 AI_INVENTORY_BROWSER_CHANNEL=chrome python -m pytest -q
```

PowerShell:

```powershell
$env:AI_INVENTORY_BROWSER_TESTS = '1'
$env:AI_INVENTORY_BROWSER_CHANNEL = 'chrome'
python -m pytest -q
```

Alternatively, install Chromium with `python -m playwright install chromium` and leave `AI_INVENTORY_BROWSER_CHANNEL` unset. Browser tests use temporary servers/databases and synthetic records. They cover upload/mapping, ambiguous choices, missing fields, worksheet selection, source correction/re-upload, downloads, row clicks, keyboard access, filters/pagination on return, direct record links, refresh, retry, HTML escaping and mobile overflow.

The private check is enabled with `AI_INVENTORY_AGENT_SNAPSHOT=/path/to/sample.csv` (PowerShell: set `$env:AI_INVENTORY_AGENT_SNAPSHOT`). It verifies all 249 reference rows are preserved, 249 nonnumeric LLM counts are flagged, and 5 test-only descriptions are identified. Private company data is excluded from this repository.

On Python 3.12.7/macOS, parsing and validation took about **0.16 seconds for 1,000 records** and **1.5 seconds for 10,000 records**, excluding persistence/browser rendering. A copy of the existing history database was also migrated and both report types exported successfully, with all original snapshot/upload hashes unchanged.

## Remaining limits

- No built-in login/SSO. The startup binds to localhost. A shared admin deployment needs an authenticated company hosting layer; allowed-host configuration does not authenticate users.
- One source column maps to one inventory field. No split/join transformations, value-remapping editor, rule builder or record editing is included. Correct the source externally and upload it again.
- Name and purpose checks are deterministic, not identity or semantic verification. Email delivery and directory membership are not checked.
- Mapping previews show up to three distinct values sampled from the first 50 records. Refreshing before confirmation discards that unsaved upload; select the file again.
- Dates in slash notation use US month/day order. Excel formulas must be replaced with values for inventory validation.
- The app is verified on macOS/Chrome; it has not been executed on a Windows host. Setup uses portable Python/pip commands and the repository's source ZIP.

## Shareable files

```text
app.py                     HTTP routes and local startup
assets/
  index.html               Upload, mapping, review and record views
  style.css                Dark responsive interface
  app.js                   Mapping, navigation, filtering and downloads
  centene-logo.jpg          Bundled Centene logo
inventory/
  __init__.py              Inventory contract, choices and header hints
  ingestion.py             Generic CSV/XLSX parser and mapping confirmation
  normalization.py         Value parsing without changing originals
  validation.py            Executable rule catalogue and per-record checks
  storage.py               SQLite history, migration and mapping memory
  exports.py               Shared filters and traceable CSV reports
tests/
  test_inventory.py        Mapping, rules, persistence and report checks
  test_app.py               HTTP and optional browser acceptance tests
example.csv                Three synthetic records
requirements.txt           Runtime and standard test dependencies
README.md                  Setup, workflow, tests and limitations
.gitignore                 Local data and generated-file exclusions
```

**17 files.** Databases, uploaded company data, virtual environments, caches and original handoff documents are excluded. No remote fonts/assets are loaded, and uploaded data is not sent to external services.
