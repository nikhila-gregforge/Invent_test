"""Lossless normalization. Unparseable cells stay available in original source inputs."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
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
    submitted = whitespace(value)
    lowered = submitted.casefold()
    for label, canonical in enum_labels(field):
        if lowered == label:
            return canonical, ''
        if lowered.startswith(label):
            suffix = submitted[len(label):]
            match = re.fullmatch(r'(?: = |:\s*| - )(.+)', suffix)
            if match:
                return canonical, match[1].strip()
    raise ValueError('Choose a configured category; unrecognized text is not automatically Other.')


def count(value):
    s = text(value)
    if not s:
        return None, 'not_provided'
    if s.casefold() in {'unknown','tbd','not available'}:
        return None, 'unknown'
    if isinstance(value, bool) or not re.fullmatch(r'\+?\d+(?:\.\d+)?', s):
        raise ValueError('Enter a nonnegative whole number, Unknown, or leave blank if optional.')
    try:
        n = Decimal(s)
        if not n.is_finite() or n != n.to_integral_value():
            raise ValueError('Fractional counts are not allowed.')
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
    raise ValueError('Use YYYY-MM-DD, M/D/YYYY, M/D/YY, or an Excel date cell.')


def impact(value):
    s = whitespace(value)
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
    s = whitespace(value)
    override = 'Unknown'
    # Override is extracted only as a named pair, never inferred from oversight.
    pair = re.search(r'\s*[,;]\s*Override(?: capability)?\s*[:= ]\s*(Yes|No|Unknown)\s*$', s, re.I)
    if pair:
        override = pair[1].title()
        s = s[:pair.start()]
    elif re.search(r'\boverride\b', s, re.I):
        raise ValueError('Use a named Override: Yes, No, or Unknown value.')
    oversight, detail = category(s, 'human_oversight')
    return oversight, override, detail


def normalize(inputs, formulas=()):
    product, problems = {}, []
    details = {}
    for field in config.FIELDS.values():
        value = inputs.get(field,'')
        product[field] = [] if field in config.MULTI else None
        try:
            if field in formulas:
                raise ValueError('Formula cells are not accepted; replace the formula with a literal value.')
            if field in config.COUNTS:
                product[field],product[field+'_state'] = count(value)
            elif field in config.DATES:
                product[field] = parse_date(value)
            elif field == 'impact':
                product[field] = impact(value) if text(value) else None
            elif field == 'human_oversight':
                if text(value):
                    product[field],product['override_capability'],detail = hitl(value)
                    if detail and product[field] == 'Other': details[field] = detail
                else:
                    product['override_capability'] = 'Unknown'
                if product[field] == 'Other' and not details.get(field):
                    raise ValueError('Other requires an explanation.')
            elif field in config.OPTIONS:
                selections = [s.strip() for s in text(value).split(';') if s.strip()]
                if field not in config.MULTI and len(selections) > 1:
                    raise ValueError('Select exactly one category.')
                parsed = []
                for selection in selections:
                    canonical,detail = category(selection,field)
                    if canonical == 'Other':
                        if not detail:
                            raise ValueError('Other requires an explanation.')
                        details[field] = detail
                    if canonical not in parsed: parsed.append(canonical)
                product[field] = parsed if field in config.MULTI else (parsed[0] if parsed else None)
            else:
                product[field] = text(value)
        except (ValueError, OverflowError) as exc:
            if field in config.COUNTS: product[field+'_state'] = 'not_provided'
            problems.append((field,str(exc)))
    product.setdefault('override_capability','Unknown')
    product['other_details'] = details
    return product, problems
