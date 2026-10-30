# AI Inventory · AI Governance Team

A dark, read-only inventory validation workspace for admins. Upload a CSV file using the fixed AI Inventory columns, inspect errors on each record, and download reports. Other upload formats are not accepted. Built with Flask, HTML/CSS/JavaScript and SQLite. No frontend build or external service is required.

## Setup

Get the source from [Invent_test](https://github.com/nikhila-gregforge/Invent_test) using **Code → Download ZIP**, then extract it. Open a terminal in the folder containing `app.py` and `requirements.txt`. You can name the extracted folder `centen_project`.

Alternatively:

```bash
git clone https://github.com/nikhila-gregforge/Invent_test.git centen_project
cd centen_project
```

Use Python **3.10 or newer** and pip (tested with Python 3.12.7):

```bash
python -m pip install -r requirements.txt
python app.py
```

These commands work in Windows PowerShell, macOS and Linux. If Python is named `python3` on your system, substitute that command. SQLite is included with Python. No virtual environment or additional package manager is required.

Open **http://127.0.0.1:8501**. Waitress serves the app on localhost. Stop with Ctrl+C.

## Test the experience

1. Choose **Upload file**. Download the empty **inventory template** to see the exact headers, or select the bundled `example.csv` and click **Validate file**.
2. Expect **3 total records, 2 records with errors, 1 passed**. The table initially shows the two records with errors. There is no column-matching step.
3. Select **LLM Count** under **Errors in field**. Only `APP-002` remains. Click any cell in its row. The record view highlights the submitted count `-1` and explains that model counts cannot be negative. **How to fix** tells you what to correct in the source.
4. Use **Back to results**. The field filter and page are preserved. Open **Download report → Errors report** with **Current view** selected. It includes errors for `APP-002`. Choose **Entire file → Records report** to include all three records.
5. Correct `example.csv` externally: change `APP-002`'s LLM count to `2`, and `APP-003`'s State from `None; California` to `California`. Upload the changed file. Expect **3 passed** in a new review; the first review is unchanged.
6. Rename `Business Owner` to `Owner` in a copy and upload it. The upload stays open and lists **Missing columns: Business Owner** and **Unexpected columns: Owner**. No record review is created. Correct the header externally and upload again.
7. To check descriptive errors, leave Business Purpose blank or change a count to `Auto`. Each affected record shows an error with a source correction instruction. A real purpose such as “Automates regression testing for claims applications” remains acceptable.
8. Restart the app. Both saved reviews remain available. Record URLs support refresh and browser Back/Forward. Record values have no editing controls.
9. From **Reviews**, choose **Delete** beside a review. Confirm **Delete review** to remove that saved review and its uploaded copy, or choose **Cancel** to keep it. Other reviews and your original CSV file remain available.

The example is synthetic and uses 2026 dates. Automated fixtures use an explicit validation date.

The current real input is `AI Inventory data.csv` in the repository root, exported from the second tab (**AI Inventory data**, 173 records) of `~/Downloads/Krisp_data.xlsx` into the 23-column inventory template. The source workbook remains unchanged. The two CSVs from the earlier ZIP are excluded. The inventory CSV is included in this repository alongside the synthetic `example.csv`. Local saved review databases and historical database backups remain under the ignored `data/` folder.

## Leadership presentation

The [validation review](presentation/AI-Inventory-Validation-Review.pptx) contains 19 slides for a 20–30 minute discussion of current findings, source corrections and proposed checks. Each slide names the AI Inventory columns involved. Speaker notes include the evidence, source rows and discussion questions. Multi-column app images include validation concentration. Most authored slide text follows ASD-STE100 principles, with exact technical names and source quotations retained.

The earlier [portfolio presentation](presentation/AI-Inventory-Product-Patterns.pptx) is preserved separately. Supporting app screenshots for both decks are in [presentation/screenshots](presentation/screenshots/). The validation review uses one source row as one record and all 173 records as its percentage denominator. Overlapping groups are not additive.

## Required file format

Use **these 23 template headers**, optionally adding **Lifecycle**. Lifecycle is preserved in record details and records reports without validation; its values may be blank or contain any text. Names, capitalization, spaces and punctuation must match. Column order may vary. No other extra columns, blank headers, duplicate headers, alternate names, or long Forms question headers are accepted in the template layout. The complete 25-column Centene export layout is also supported, preserving Lifecycle and User AIS as source data.

| # | Column header |
| --- | --- |
| 1 | Application / System ID |
| 2 | AI System / Solution Name |
| 3 | Business Purpose / Intended Use |
| 4 | Business Function |
| 5 | Impact from AI (Patient/Member, Regulatory, Financial) |
| 6 | Business Owner |
| 7 | Technical Owner |
| 8 | Vendor Owner |
| 9 | Source of AI System |
| 10 | Type(s) of AI Used |
| 11 | ML/DL Models Count |
| 12 | LLM Count |
| 13 | Data Input to or Processed by AI Tool |
| 14 | Data Environment |
| 15 | Deployment Environment |
| 16 | Deployment Status |
| 17 | Go-Live Date |
| 18 | LOB |
| 19 | State |
| 20 | Risk Tier |
| 21 | Human-in-the-Loop |
| 22 | Submitter Name |
| 23 | Date Submitted |

All columns must exist. **Cell values** for Vendor Owner, the two model counts, and Go-Live Date are optional or conditional under the rules below. The other 19 fields require values. There is no separate source-record-ID column; Application / System ID and the source row number identify each record.

The first 21 names follow the AI Inventory reference headings. Submitter Name and Date Submitted remain separate inventory fields. The template, parser, field help and reports use the same central contract in `inventory/__init__.py`. The empty CSV template is generated by `/api/template`, so no separate template file needs to be maintained.

Only **CSV files (`.csv`, case-insensitive)** are accepted, with limits of **10 MiB / 10,000 data rows**. The file picker and server enforce this restriction. XLSX, XLS, PDF, JSON, TSV, TXT and other formats are rejected without saving a review. Export spreadsheet data as CSV before uploading; renaming a workbook to `.csv` does not convert it. CSV accepts UTF-8/BOM and Windows-1252. Header checks run before record checks. Structural failures such as malformed CSV rows stop the upload and do not save a review. Blank interior records receive their own missing-value errors; trailing empty rows are ignored.

## Validation behavior

Only two record outcomes exist:

- **Errors:** one or more definite validation errors.
- **Passed:** all applicable configured checks complete without errors.

A failing record does not block valid records. Repeated application IDs flag the matching rows. A cross-field error counts once even when both fields are highlighted. A check blocked by another invalid field points to the underlying error; it cannot cause an incomplete record to appear Passed.

Every error supplies the submitted value, a plain-language problem, and **How to fix** guidance. Rule IDs and exact requirements are secondary details. **View validation rules** shows formats, examples and conditional requirements. The example choice catalogue is not an exhaustive allowlist. The executable catalogue in `inventory/validation.py` supplies the checks, field help and error reports.

Rules version **5.4** follows `rules/validation_layers.txt`, with the confirmed allowances for owner names, multiple contacts, any valid email domain and future go-live dates. The vendor-contact requirement applies when the source establishes vendor involvement. The retained checks include:

- Required values and nonblank selections. System names, purposes, combined impact profiles and other text do not require special wording. Choices outside the examples are accepted. Other does not require a prefixed explanation.
- Business and technical owners accept a name or a syntactically valid email from any domain, including `@mhplan.com`. When email text is supplied, it must contain at least one valid address. Multiple contacts and notes are accepted. Missing-contact placeholders do not identify an owner. Vendor emails also accept any domain. No directory or delivery check is performed.
- Counts must be nonnegative whole numbers; explicit numeric counts with notes are accepted. ML, DL and Predictive Analytics require an ML/DL count of at least **1**. LLM, GenAI and Agentic AI require a numeric LLM count of at least **0**. Blank, Unknown and Not Applicable are accepted when the corresponding count is not required. Model names, ambiguous ranges and fractions are not numeric counts.
- Active systems require a valid go-live date. Future go-live dates are accepted for every deployment status. Submission dates cannot be in the future. Dates accept `YYYY-MM-DD`, `M/D/YYYY` and `M/D/YY`.
- Vendor-built, licensed, purchased and hybrid sources require a vendor contact. A platform name such as Copilot Studio, Other, Unknown or uncertain plans alone do not establish vendor involvement. Missing contacts flag Vendor Owner only; the source is the condition, not an erroneous field. In-house systems may leave Vendor Owner blank or Not Applicable.
- None cannot be combined with other LOB or state selections. All States cannot be combined with individual states or None. Medicaid with State None does not independently create an error.
- Actual application IDs must be unique within a file. Repeated unavailable-ID placeholders and system names are allowed.
- CSV cells remain literal source text. No formulas are evaluated. Formula text in numeric/date fields fails the format check; downloaded reports escape formula-like text for spreadsheet safety.

Lifecycle is retained as source data and is not validated. Text that cannot be assigned to a chart category is reported as **Unclassified**, which does not make the record an error.
## Results and reports

The home page contains upload access and recent reviews, with a **Delete** button for each review. Results show **Total records / Records with errors / Passed**, search, an **All records / Errors / Passed** filter, an inventory-field error filter, and the record table. New reviews start with errors when present and show all records when everything passes. Rule-version numbers are not displayed in the interface.

Search covers system name, application ID and business owner. **Errors in field** selects records with an error involving that field. Click any record row to open read-only details with error fields first.

**Explore more inventory fields → Visualize → + Add field** builds a drill-down with **two to five columns**, chosen from the supported categorical inventory fields. The Add field control stops at five. **Remove field** removes the last level.

The comparison is a **16:9 analysis canvas** with a chart and table at every selected level. Three columns appear side by side; four and five use two rows. For **LOB → AI source group → Deployment status**, select Medicaid in the first table, then Developed in-house in the second, to see deployment within that exact intersection. The highlighted category path connects the levels, and the headline reports how many distinct records match the complete path. All selected fields remain visible. Selecting a category updates the following levels; adding another field preserves the existing selections. **Reset path** returns to the largest category at each level.

Charts show record counts, with an explicit count scale. Red segments show records with validation findings; teal segments show records with no findings. Each table has separate **Records** and **Flagged** counts. Tables use **% of all records in the file** by default. **Percentage basis → Records in the parent group** instead divides by the record count entering each level. The denominator is labeled in every panel and included in CSV downloads. One source row represents one record. Multi-select categories can overlap, so do not add category counts or successive levels. Missing, invalid and unclassified categories remain included. Record counts open their underlying records with every ancestor selection applied; flagged counts open only records with findings.

The **Validation concentration** panel counts distinct records with findings, separately from finding instances. Use **Concentration scope** to inspect the current analytics view or only the selected path. Use **Group findings by** to compare finding families, inventory columns or validation rules. A record counts once within each group, but groups can overlap. Column groups include all columns used by a finding, including those that trigger conditional checks. The panel shows up to seven groups, with all groups included in CSV. Group counts open the matching records. Filters and the concentration scope are printed in the canvas and PNG.

**Review selected records** opens a correction queue for the complete selected path. Category counts, flagged counts and concentration groups also open queues for their exact selection. Each queue shows the path, owners, responsible AI Inventory columns, submitted values, findings and fix instructions. It includes all saved findings on each selected record. **Download selected records (CSV)** exports every record in that queue, across all pages, with one CSV row per record. Repeated findings stay together on that row. The selection count and whole-file baseline are separate metadata; broader table filters do not replace the selected queue. Correct values in the source file and upload again to validate them.

Each panel displays up to six categories in the three-column layout, or three categories in the denser four/five-column layout. Category paging keeps the canvas readable. A page indicator identifies the visible subset, and a chart notes if its selected category is on another page. **Chart** opens the full distribution for that level, with summary CSV, chart PNG and underlying-record access.

**Export slide (PNG)** saves the complete canvas at **1920 × 1080**, ready for a widescreen PowerPoint slide. It includes the same path, tables, category pages, charts, validation concentration, scope and percentage basis shown on screen, with a light presentation background. The image explicitly labels the current category page; it does not silently crop a long hierarchy. **Download data (CSV)** includes every category for every level in the focused path, including categories on other pages, with parent paths, distinct record counts, flagged counts, percentage denominators and selection flags. Additional rows contain all validation-concentration groups and their scope. It exports the current drill-down rather than all possible category combinations.

Drilling and category paging reuse the saved category memberships and finding metadata without additional network requests. **Entire file** includes all records; **Current filters** includes matching records across every record-table page. The overall percentage denominator continues to use the whole uploaded file. The surrounding review page and ordinary single-field charts retain their existing layout. The optional **AI source group** combines configured vendor source categories into Vendor AI while retaining original values.

The two CSV reports use the same selection as the table:

- **Errors report:** all errors on selected records, including source row, application ID, inventory fields, submitted values, problem, fix and requirement.
- **Records report:** one row per selected record, its status/error count, any checks blocked by errors, and all original source values. Original field columns use the prefix `Source: ` to distinguish them from report metadata.

**Current view** includes filtered records across every page. **Entire file** ignores filters. Reports include the run ID, original filename, inventory format, rules version and validation date. The worksheet column is retained for historical reports and is blank for new CSV uploads. Empty selections produce header-only CSVs. UTF-8 BOM supports spreadsheet opening, and formula-like values are prefixed with an apostrophe for spreadsheet safety. Original inputs remain unchanged in SQLite.

## Persistence and earlier reviews

`data/validations.sqlite3` stores original upload bytes and result snapshots that remain unchanged until explicitly deleted. Fixed-format reviews use `inventory_runs`. Identical file content, worksheet, inventory format, rules version and validation date reopen the same saved review. Changed content, rules or date produce a separate review.

Deleting a review removes its snapshot and uploaded copy from the active database. This applies to current and archived reviews and cannot be undone in the app. Other reviews, the original file on your computer, and existing backup files are unaffected. Uploading the same file after deleting its review creates a new review.

Rules version **5.4** removes the Centene-only owner-email restriction. Upload the same file again to create a review under the new rules; earlier snapshots remain unchanged. Previously saved fixed-format reviews, including workbook reviews, retain their original snapshots and remain readable. New workbook uploads are rejected.

Earlier `validation_runs` tables are preserved byte-for-byte at the snapshot/upload level during migration. Their history entries show **Upload again to review** and a notice explaining that a current-format upload is needed. They are never relabeled Passed, and old results are not mixed into current reports. Archived detail/report requests return the same re-upload notice. Legacy snapshots remain available in the database unless explicitly deleted.

When an older history database is first opened, a backup is saved as `data/validations-before-strict.sqlite3` before creating the new table. Existing historical tables and the former onboarding `data/inventory.sqlite3` are left intact. To back up, stop the application and copy `data/`.

Expected upload problems appear in the UI. Unexpected server failures return a generic error and log the exception type in the terminal without submitted values. There is no persistent failure-log dashboard.

| Environment variable | Default |
| --- | --- |
| `PORT` | `8501` |
| `AI_INVENTORY_DATA_DIR` | `./data` |
| `AI_INVENTORY_MAX_BYTES` | `10485760` |
| `AI_INVENTORY_MAX_ROWS` | `10000` |
| `AI_INVENTORY_HOSTS` | `localhost,127.0.0.1,[::1]` |

For another port, use `PORT=8502 python app.py` on macOS/Linux, or `$env:PORT = '8502'` followed by `python app.py` in PowerShell.

## Acceptance tests

```bash
python -m pytest -q -s
```

The default suite skips eleven optional browser tests and one private input-reference check. Enable browser tests separately as described below.

Coverage includes CSV-only enforcement, rejected formats and renamed non-CSV content, strict/reordered headers, template consistency, missing/extra/blank/duplicate columns, per-record errors, permitted former advisory cases, names/emails, conditional rules and dependencies, CSV parsing, source preservation, concurrent uploads, history deduplication, archived reviews, review deletion, filtered reports, safe downloads and read-only record endpoints.

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

Alternatively, install Chromium with `python -m playwright install chromium` and leave `AI_INVENTORY_BROWSER_CHANNEL` unset. Tests use isolated servers/databases and synthetic records. They cover direct upload, CSV-only selection and rejection, template download, header errors, corrected re-upload, actionable record errors, filtering/downloads, row clicks, keyboard access, Back/Forward, refresh, retries, archived notices, HTML escaping and mobile overflow. Review deletion covers cancellation, retry after a failed request, persistence after refresh and the empty state after deleting the final review.

To run the private reference check, set `AI_INVENTORY_AGENT_SNAPSHOT` to the original source export path. It verifies that the former nonstandard export is rejected with missing/unexpected header details. It does not infer columns, modify the file, or bundle private company data.

On Python 3.12.7/macOS, parsing and validation took about **0.14 seconds for 1,000 records** and **1.4 seconds for 10,000 records**, excluding persistence/browser rendering. An isolated copy of the existing history was upgraded successfully; original snapshot/upload hashes remained unchanged.

## Remaining limits

- No built-in login or SSO. Startup binds to localhost. Shared admin hosting needs an authenticated company hosting layer; allowed-host settings alone do not authenticate users.
- Columns must match the template exactly. Correct file headers and values externally, then upload again. No record editor, column conversion or rule builder is included.
- Names and purposes are checked for required values; their truth or meaning is not verified.
- Slash dates use US month/day order. Spreadsheet files must be exported as CSV with actual values before uploading.
- Verified on macOS/Chrome; execution on a Windows host has not been tested. Setup uses portable Python/pip commands and GitHub's source ZIP.

## Shareable files

```text
app.py                     HTTP routes, template download and local startup
assets/
  index.html               Upload, review and read-only record views
  style.css                Dark responsive interface
  app.js                   Navigation, review deletion, filtering and downloads
  charts.js                Inventory charts and record percentages
  comparison.js            Linked drill-down tables and charts (up to five levels)
  comparison-export.js     Widescreen PNG and complete category CSV exports
  chart-actions.js         Chart downloads and underlying-record views
  centene-logo.jpg          Bundled Centene logo
inventory/
  __init__.py              Fixed inventory columns, values and field guidance
  ingestion.py             CSV-only enforcement and strict parsing
  normalization.py         Value parsing without changing originals
  validation.py            Error rules and actionable fixes
  storage.py               SQLite reviews and preserved historical snapshots
  exports.py               Shared filters and CSV reports
  analytics.py             Chart categories, counts and record percentages
  chart_actions.py         Chart membership for underlying-record views
rules/
  validation_layers.txt    Supplied validation requirements
tests/
  test_inventory.py        Contract, rules, persistence and report checks
  test_app.py               HTTP and optional browser acceptance tests
  test_analytics.py         Chart categories and record percentage checks
  test_centene_export.py    Centene export parsing with synthetic fixtures
  test_validation_layers.py Validation requirements and agreed allowances
example.csv                Three synthetic records in the required format
requirements.txt           Runtime and standard test dependencies
README.md                  Setup, workflow, tests and limitations
.gitignore                 Local data and generated-file exclusions
```

The input CSVs and presentation files are included in this repository. Local databases under `data/`, virtual environments, caches and temporary SQLite journal files are excluded. The app loads no remote assets or fonts and sends no uploaded data to external services.
