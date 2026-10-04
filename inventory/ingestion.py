"""Strict disclosure parsing, preserving source cells and row locators."""
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from io import BytesIO, StringIO
from pathlib import Path
import re
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl import load_workbook
import inventory as config

class ImportFailure(ValueError):
    pass

class SheetSelectionRequired(ImportFailure):
    def __init__(self, sheets):
        self.sheets = sheets
        super().__init__('Select a worksheet containing the disclosure export.')

@dataclass
class ParsedFile:
    rows: list
    sheet: str
    extra_headers: list
    headers: dict
    profile: str = 'forms'

def whitespace(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def _mapping(headers):
    normalized = [whitespace(h) for h in headers]
    duplicates = sorted(h for h, n in Counter(normalized).items() if n > 1)
    if duplicates:
        raise ImportFailure('Duplicate headers after whitespace normalization: ' + ', '.join(duplicates))
    agent = {'Title ID','Name'}.issubset(normalized)
    aliases = ({**config.AGENT_HEADERS, **config.AGENT_OPTIONAL, 'Date Created':'created_date'} if agent else
               {whitespace(a): q for q, names in config.HEADER_ALIASES.items() for a in names})
    mapped, extras = {}, []
    for i, h in enumerate(normalized):
        if h in aliases:
            q = aliases[h]
            if q in mapped:
                raise ImportFailure(f'Ambiguous schema: multiple headers map to {q}.')
            mapped[q] = i
        else:
            extras.append(str(headers[i]))
    required = {'response_id','system_name','business_purpose'} if agent else config.HEADER_ALIASES
    missing = [q for q in required if q not in mapped]
    if missing:
        raise ImportFailure('Missing required columns: ' + ', '.join(missing))
    return mapped, extras, 'agents' if agent else 'forms'

def _value(cell, is_id=False):
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, time):
        return {'__excel_time__': value.isoformat()}
    if isinstance(value, (date, datetime)):
        return {'__excel_date__': value.isoformat()}
    if is_id and isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            if re.fullmatch('0+', cell.number_format):
                return str(int(value)).zfill(len(cell.number_format))
            return str(int(value))
    return value

def parse_file(data, filename, sheet=None, max_bytes=None, max_rows=None):
    max_bytes = config.MAX_BYTES if max_bytes is None else max_bytes
    max_rows = config.MAX_ROWS if max_rows is None else max_rows
    if len(data) > max_bytes:
        raise ImportFailure(f'File exceeds the {max_bytes / 1024 / 1024:g} MiB limit; nothing was imported.')
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.csv','.xlsx'}:
        raise ImportFailure('Unsupported format. Upload a CSV or XLSX file.')
    workbook = None
    try:
        if suffix == '.csv':
            try:
                decoded = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                decoded = data.decode('cp1252')
            # A field may contain a long purpose; total bytes are bounded above.
            csv.field_size_limit(max_bytes)
            reader = csv.reader(StringIO(decoded, newline=''), strict=True)
            headers = next(reader, [])
            iterator = enumerate(reader, start=2)
            selected = ''
        else:
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=False)
            nonempty = []
            for ws in workbook.worksheets:
                if any(any(c.value is not None and c.value != '' for c in row) for row in ws.iter_rows()):
                    nonempty.append(ws.title)
            if not nonempty:
                raise ImportFailure('Workbook has no nonempty worksheets.')
            if sheet is None and len(nonempty) > 1:
                raise SheetSelectionRequired(nonempty)
            selected = sheet or nonempty[0]
            if selected not in nonempty:
                raise ImportFailure('Selected worksheet is missing or empty.')
            reader = iter(workbook[selected].iter_rows())
            header_cells = list(next(reader, []))
            while header_cells and header_cells[-1].value is None:
                header_cells.pop()
            headers = [c.value for c in header_cells]
            iterator = enumerate(reader, start=2)
        mapping, extras, profile = _mapping(headers)
        result, pending = [], []
        for locator, row in iterator:
            if suffix == '.xlsx':
                formulas = [q for q, i in mapping.items() if i < len(row) and row[i].data_type == 'f']
                id_indexes = {mapping[q] for q in ['ID','Q1','response_id'] if q in mapping}
                values = [_value(c, i in id_indexes) for i, c in enumerate(row)]
                while len(values) > len(headers) and values[-1] == '':
                    values.pop()
                values += [''] * max(0, len(headers) - len(values))
            else:
                formulas, values = [], row
            empty = not any(v != '' and v is not None for v in values)
            if empty:
                pending.append(locator)
                continue
            if len(values) != len(headers):
                raise ImportFailure(f'Malformed row {locator}: expected {len(headers)} cells, found {len(values)}.')
            # Empty interior rows retain locators and fail row validation; trailing rows are ignored.
            for n in pending:
                result.append({'source_row':n,'values':{q:'' for q in mapping},'metadata':{},'formulas':[]})
            pending.clear()
            result.append({'source_row':locator, 'values':{q:values[i] for q,i in mapping.items()},
                           'metadata':{str(headers[i]):v for i,v in enumerate(values) if i not in mapping.values()},
                           'formulas':formulas})
            if len(result) > max_rows:
                raise ImportFailure(f'File exceeds the {max_rows:,} data-row limit; nothing was imported.')
        if not result:
            raise ImportFailure('The file has headers but no data rows.')
        return ParsedFile(result, selected, extras, {q:str(headers[i]) for q,i in mapping.items()}, profile)
    except ImportFailure:
        raise
    except (csv.Error, UnicodeError, BadZipFile, ParseError, InvalidFileException, OSError, ValueError, KeyError, TypeError) as exc:
        raise ImportFailure('Could not read this file. Check its format, quoting, and worksheet structure.') from exc
    finally:
        if workbook:
            workbook.close()
