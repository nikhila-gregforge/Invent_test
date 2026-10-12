"""Lossless normalization. Unparseable cells stay available in original source inputs."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from html import unescape
import re
import inventory as config
from inventory.ingestion import whitespace


def text(value):
    return '' if value is None else str(value).strip()

@lru_cache(maxsize=None)
def enum_labels(field):
    return sorted({**{x.casefold():x for x in config.OPTIONS[field]},
                   **{whitespace(k).casefold():v for k,v in config.ALIASES.get(field,{}).items()}}.items(),
                  key=lambda item:len(item[0]), reverse=True)

def category(value, field):
    submitted = whitespace(unescape(text(value)))
    lowered = submitted.casefold()
    for label, canonical in enum_labels(field):
        if lowered == label:
            return canonical, ''
        if lowered.startswith(label):
            suffix = submitted[len(label):]
            match = re.fullmatch(r'(?: = |:\s*| [–—-] )(.+)', suffix)
            if field == 'ai_source' and not match:
                match = re.fullmatch(r',\s*(.+)', suffix)
            if match:
                return canonical, match[1].strip()
    # The catalogue is for recognition and charts, not an exhaustive allowlist.
    return submitted, ''


def choice_selections(value, field):
    """Split exported lists without splitting commas inside a known choice name."""
    result = []
    def label_at_start(candidate):
        lowered = candidate.casefold()
        for label, _ in enum_labels(field):
            if lowered.startswith(label):
                suffix = candidate[len(label):]
                if not suffix or suffix.lstrip().startswith(',') or re.match(r'(?: = |:\s*| [–—-] )',suffix):
                    return len(label)
        return None

    for chunk in whitespace(unescape(text(value))).split(';'):
        remaining = chunk.strip()
        while remaining:
            end = label_at_start(remaining)
            if end is None:
                value, separator, remaining = remaining.partition(',')
                if value.strip(): result.append(value.strip())
                remaining = remaining.strip() if separator else ''
                continue
            suffix = remaining[end:]
            if suffix.lstrip().startswith(','):
                suffix = suffix.lstrip()
            if suffix.startswith(','):
                result.append(remaining[:end]); remaining = suffix[1:].strip()
            elif not suffix:
                result.append(remaining); break
            else:
                # Explanations can contain commas. A comma before another known
                # choice starts a new selection; other commas stay in the detail.
                boundary = next((match.start() for match in re.finditer(',',suffix)
                                 if label_at_start(suffix[match.end():].strip()) is not None),None)
                if boundary is None:
                    result.append(remaining); break
                result.append(remaining[:end+boundary]); remaining = suffix[boundary+1:].strip()
    return result


def count(value):
    s = whitespace(unescape(text(value)))
    if not s:
        return None, 'not_provided'
    if s.casefold() in {'unknown','tbd','not available','n/a','na','none','not applicable'}:
        return None, 'unknown'
    # Accept an explicitly stated count with notes, never a model version,
    # numbered list, range, or an estimate such as "8+".
    annotated = re.fullmatch(
        r'(?:(?:ML/DL Models?|ML Models?|LLM)\s+Count\s*:\s*)?'
        r'(\+?\d+(?:\.\d+)?)'
        r'(?:\s+\([^\n]+\)\.?|\s*[-–—]\s*[A-Za-z][^\n]*|'
        r',\s+[A-Za-z][^\n]*|\s+(?:LLMs?|models?))', s, re.I)
    if annotated:
        s = annotated[1]
    if isinstance(value, bool) or not re.fullmatch(r'\+?\d+(?:\.\d+)?', s):
        raise ValueError('A model count must be a whole number of 0 or greater.')
    try:
        n = Decimal(s)
        if not n.is_finite() or n != n.to_integral_value():
            raise ValueError('This count has a fraction; only whole numbers are accepted.')
        return int(n), 'known'
    except InvalidOperation as exc:
        raise ValueError('Invalid count.') from exc


def parse_date(value):
    if isinstance(value, dict) and '__excel_date__' in value:
        value = datetime.fromisoformat(value['__excel_date__'])
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = text(value)
    if not s:
        return None
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        return date.fromisoformat(s).isoformat()
    match = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})', s)
    if match:
        m,d,y = match.groups()
        year = int(y)
        if len(y) == 2:
            year += 2000 if year <= 68 else 1900
        return date(year,int(m),int(d)).isoformat()
    raise ValueError('Use YYYY-MM-DD, M/D/YYYY, or M/D/YY.')


def impact(value):
    s = whitespace(unescape(text(value)))
    if s.casefold() == 'unknown':
        return dict.fromkeys(['member','regulatory','financial'], 'Unknown')
    result = {}
    # Patient and spaced en-dash separators are explicit variants in the supplied export.
    for pair in re.split(r'\s*[,;]\s*|\s+[–—]\s+', s):
        m = re.fullmatch(r'(Patient/Member|Member|Patient|Regulatory|Financial)\s*[:=]\s*(Yes|No|Unknown)', pair, re.I)
        if not m:
            raise ValueError('Supply Member, Regulatory, and Financial exactly once, each Yes, No, or Unknown.')
        dimension = m[1].lower()
        if dimension in {'patient/member','patient'}:
            dimension = 'member'
        if dimension in result:
            raise ValueError('Each impact dimension must appear exactly once.')
        result[dimension] = m[2].title()
    if set(result) != {'member','regulatory','financial'}:
        raise ValueError('Supply all three impact dimensions: Member, Regulatory, Financial.')
    return result


def hitl(value):
    s = whitespace(unescape(text(value)))
    override = 'Unknown'
    # Override is extracted only as a named pair, never inferred from oversight.
    pair = re.search(r'\s*[,;]\s*Override(?: capability)?\s*[:= ]\s*(Yes|No|Unknown)\s*$', s, re.I)
    if pair:
        override = pair[1].title()
        s = s[:pair.start()]
    oversight, detail = category(s, 'human_oversight')
    return oversight, override, detail


def normalize(inputs):
    product, problems = {}, []
    details = {}
    for field in config.FIELDS.values():
        value = inputs.get(field,'')
        product[field] = [] if field in config.MULTI else None
        try:
            if field in config.COUNTS:
                product[field],product[field+'_state'] = count(value)
            elif field in config.DATES:
                product[field] = parse_date(value)
            elif field == 'impact':
                try:
                    product[field] = impact(value) if text(value) else None
                except ValueError:
                    # A combined profile or free-text response satisfies Q5.
                    # Individual chart dimensions may remain unclassified.
                    product[field] = text(value)
            elif field == 'human_oversight':
                if text(value):
                    product[field],product['override_capability'],detail = hitl(value)
                    if detail and product[field] == 'Other': details[field] = detail
                else:
                    product['override_capability'] = 'Unknown'
            elif field in config.OPTIONS:
                submitted = unescape(text(value))
                if field in config.MULTI:
                    selections = choice_selections(value,field)
                elif field == 'deployment_status':
                    selections = [s.strip() for s in submitted.split(';') if s.strip()]
                else:
                    selections = [submitted] if submitted else []
                if text(value) and not selections:
                    raise ValueError('Select at least one value; separators alone are not a selection.')
                if field not in config.MULTI and len(selections) > 1:
                    raise ValueError('Select exactly one category.')
                parsed = []
                for selection in selections:
                    canonical,detail = category(selection,field)
                    if canonical == 'Other' and detail:
                        details[field] = detail
                    if canonical not in parsed: parsed.append(canonical)
                product[field] = parsed if field in config.MULTI else (parsed[0] if parsed else None)
            else:
                product[field] = text(value)
            if field in config.OPTIONS or field == 'impact':
                if text(value) and not unescape(text(value)).strip(' ;,\t\r\n'):
                    raise ValueError('Select at least one value; separators alone are not a selection.')
        except (ValueError, OverflowError) as exc:
            if field in config.COUNTS: product[field+'_state'] = 'not_provided'
            problems.append((field,str(exc)))
    product.setdefault('override_capability','Unknown')
    product['other_details'] = details
    return product, problems
