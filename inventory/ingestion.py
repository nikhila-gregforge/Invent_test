"""Read CSV files that use the exact inventory column contract."""
import csv
from collections import Counter
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import re
import inventory as config


class ImportFailure(ValueError):
    pass


@dataclass
class ParsedFile:
    rows: list
    sheet: str
    columns: list
    field_columns: dict
    layout: str


def whitespace(value):
    return re.sub(r'\s+', ' ', '' if value is None else str(value)).strip()


def header_key(value):
    return whitespace(value).casefold()


class HeaderMismatch(ImportFailure):
    def __init__(self, headers, expected=None):
        expected = config.HEADERS if expected is None else expected
        self.missing = [h for h in expected if h not in headers]
        self.unexpected = list(dict.fromkeys(h for h in headers if h and h not in expected))
        counts = Counter(header_key(h) for h in headers if whitespace(h))
        self.duplicates = list(dict.fromkeys(h for h in headers if whitespace(h) and counts[header_key(h)] > 1))
        self.blank_columns = [i+1 for i,h in enumerate(headers) if not whitespace(h)]
        super().__init__('The column headers do not match a supported AI Inventory layout. Fix the headers in your file and upload it again.')

    def details(self):
        return dict(missing=self.missing,unexpected=self.unexpected,duplicates=self.duplicates,blank_columns=self.blank_columns)


def check_headers(headers):
    # Complete layouts only: no inferred columns or arbitrary mixtures of aliases.
    layout, columns = max(config.INPUT_LAYOUTS.items(), key=lambda item:len(set(headers) & set(item[1])))
    error = HeaderMismatch(headers,columns)
    if error.missing or error.unexpected or error.duplicates or error.blank_columns:
        raise error
    return layout,{field:header for header,field in columns.items() if field is not None}


def parse_file(data, filename, max_bytes=None, max_rows=None):
    max_bytes = config.MAX_BYTES if max_bytes is None else max_bytes
    max_rows = config.MAX_ROWS if max_rows is None else max_rows
    if len(data) > max_bytes:
        raise ImportFailure(f'File exceeds the {max_bytes / 1024 / 1024:g} MiB limit.')
    suffix = Path(filename).suffix.lower()
    if suffix != '.csv':
        raise ImportFailure('Only CSV files are accepted. Export your inventory as a .csv file and upload it again.')
    try:
        try:
            decoded = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = data.decode('cp1252')
        csv.field_size_limit(max_bytes)
        reader = csv.reader(StringIO(decoded,newline=''),strict=True)
        headers = next(reader,[])
        layout,field_columns = check_headers(headers)
        result, pending = [], []
        for locator,values in enumerate(reader,start=2):
            if not any(v is not None and v != '' for v in values):
                pending.append(locator)
                continue
            if len(values) != len(headers):
                raise ImportFailure(f'Row {locator} has {len(values)} cells; the header has {len(headers)} columns.')
            if len(result)+len(pending)+1 > max_rows:
                raise ImportFailure(f'File exceeds the {max_rows:,} data-row limit.')
            for n in pending:
                result.append({'source_row':n,'values':dict.fromkeys(headers,'')})
            pending.clear()
            result.append({'source_row':locator,'values':dict(zip(headers,values))})
        if not result:
            raise ImportFailure('The file has headers but no data rows.')
        # Keep the saved-review shape compatible with historical worksheet uploads.
        return ParsedFile(result,'',headers,field_columns,layout)
    except ImportFailure:
        raise
    except (csv.Error,UnicodeError,ValueError,OverflowError) as exc:
        raise ImportFailure('Could not read this CSV file. Check its encoding, quoting, and row structure.') from exc
