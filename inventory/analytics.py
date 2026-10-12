"""Categorical distributions with explicit denominators and missing-value accounting."""
from collections import Counter
import inventory as config
from inventory.normalization import normalize, text


# IDs, names, contact details, descriptions, dates and numeric model counts do not
# describe mutually exclusive categories, so they are deliberately not pie charts.
CHARTS = [
    ('risk_tier', 'Risk tier', 'pie'),
    ('deployment_status', 'Deployment status', 'pie'),
    ('lines_of_business', 'Line of business', 'bar'),
    ('human_oversight', 'Human oversight', 'pie'),
    ('ai_source', 'Source of AI system', 'pie'),
    ('deployment_environment', 'Deployment environment', 'pie'),
    ('ai_types', 'AI technologies', 'bar'),
    ('business_functions', 'Business functions', 'bar'),
    ('data_types', 'Data processed', 'bar'),
    ('data_environments', 'Data environments', 'bar'),
    ('states', 'States / usage scope', 'bar'),
    ('impact.member', 'Patient / member impact', 'pie'),
    ('impact.regulatory', 'Regulatory impact', 'pie'),
    ('impact.financial', 'Financial impact', 'pie'),
]
INVALID_CHART_RULES = {'REQ-01', 'ENUM-01', 'IMPACT-01', 'SCOPE-01'}


def inventory_error_count(records):
    """Count each record once for errors in Q1–Q21; Q22/Q23 remain validated."""
    fields = set(config.INVENTORY_FIELDS[:21])
    return sum(any(fields.intersection(issue['fields']) for issue in record['findings']) for record in records)


def invalid_chart_fields(findings):
    return sorted({field for issue in findings if issue['rule_id'] in INVALID_CHART_RULES
                   for field in issue['fields']})


def distributions(snapshot, records):
    definitions = {field['id']: field for field in snapshot['fields']}
    prepared = []
    for record in records:
        product = record.get('normalized')
        if product is None:
            # Older snapshots have original cells and findings, but no parsed values.
            # This derives chart categories only; saved validation outcomes never change.
            product, problems = normalize(record['cells'])
            invalid = set(dict(problems)) | set(invalid_chart_fields(record['findings']))
        else:
            invalid = set(record['chart_invalid_fields'])
        prepared.append((record['cells'], product, invalid))

    charts = []
    for chart_id, title, kind in CHARTS:
        field, _, dimension = chart_id.partition('.')
        multi = field in config.MULTI
        options = (['Yes', 'No', 'Unknown'] if dimension else
                   ['High', 'Medium', 'Low', 'Unknown'] if field == 'risk_tier' else
                   definitions.get(field, {}).get('options', []))
        counts = Counter()
        missing = invalid = valid = unclassified = 0
        for cells, product, invalid_fields in prepared:
            value = product.get(field)
            if not text(cells.get(field)):
                missing += 1
            elif field in invalid_fields or value is None or value == []:
                invalid += 1
            else:
                selections = [value.get(dimension)] if dimension and isinstance(value, dict) else value if multi else [value]
                if not isinstance(selections, list) or any(item not in options for item in selections):
                    unclassified += 1
                    continue
                valid += 1
                counts.update(dict.fromkeys(selections, 1))

        selection_count = sum(counts.values())
        denominator = len(records)
        labels = [label for label in options if counts[label] or field == 'risk_tier']
        if not multi:
            for label, count in [('Missing', missing), ('Invalid', invalid), ('Unclassified', unclassified)]:
                if count:
                    counts[label] = count
                    labels.append(label)
        if kind == 'bar':
            labels.sort(key=lambda label: (-counts[label], label))
        buckets = [{'label': label, 'count': counts[label],
                    'percent': round(100 * counts[label] / denominator, 2) if denominator else 0,
                    'record_percent': round(100 * counts[label] / len(records), 2) if records else 0,
                    'color_index': options.index(label) if label in options else -1}
                   for label in labels]
        charts.append({'id': chart_id, 'title': title, 'kind': kind, 'multi': multi,
                       'total_records': len(records), 'valid_records': valid,
                       'missing_records': missing, 'invalid_records': invalid,
                       'unclassified_records': unclassified,
                       'selection_count': selection_count, 'denominator': denominator,
                       'buckets': buckets})
    return {'total_records': len(records), 'charts': charts}
