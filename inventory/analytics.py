"""Categorical distributions with explicit denominators and missing-value accounting."""

from collections import Counter

import inventory as config
from inventory.normalization import normalize, text


CHARTS = [
    ("risk_tier", "Risk tier", "pie"),
    ("deployment_status", "Deployment status", "pie"),
    ("lines_of_business", "Line of business", "bar"),
    ("human_oversight", "Human oversight", "pie"),
    ("ai_source", "Source of AI system", "pie"),
    ("ai_source_group", "AI source group", "pie"),
    ("deployment_environment", "Deployment environment", "pie"),
    ("ai_types", "AI technologies", "bar"),
    ("business_functions", "Business functions", "bar"),
    ("data_types", "Data processed", "bar"),
    ("data_environments", "Data environments", "bar"),
    ("states", "States / usage scope", "bar"),
    ("impact.member", "Patient / member impact", "pie"),
    ("impact.regulatory", "Regulatory impact", "pie"),
    ("impact.financial", "Financial impact", "pie"),
]

INVALID_CHART_RULES = {
    "REQ-01",
    "ENUM-01",
    "IMPACT-01",
    "SCOPE-01",
}

SOURCE_GROUP_NOTE = (
    "Vendor AI combines Custom-built by third-party vendor for Centene, "
    "Licensed from third-party vendor (customized), Purchased off-the-shelf "
    "(no modifications), and Hybrid (in-house + vendor components). "
    "Approved Vendor built aliases are included. Other source values are "
    "Unclassified; blank and invalid entries remain separate. "
    "Original source values are retained."
)


def inventory_error_count(records):
    """Count each record once for errors in Q1–Q21."""

    fields = set(config.INVENTORY_FIELDS[:21])

    return sum(
        any(
            fields.intersection(issue["fields"])
            for issue in record["findings"]
        )
        for record in records
    )


def invalid_chart_fields(findings):
    return sorted({
        field
        for issue in findings
        if issue["rule_id"] in INVALID_CHART_RULES
        for field in issue["fields"]
    })


def _prepare(records):
    prepared = []

    for record in records:
        product = record.get("normalized")

        if product is None:
            # Historical snapshots may lack normalized chart values.
            # Saved validation outcomes are never changed here.
            product, problems = normalize(record["cells"])

            invalid = (
                set(dict(problems))
                | set(invalid_chart_fields(record["findings"]))
            )
        else:
            invalid = set(record["chart_invalid_fields"])

        prepared.append((record["cells"], product, invalid))

    return prepared


def _definition(snapshot, chart_id):
    supported = {
        identifier: (title, kind)
        for identifier, title, kind in CHARTS
    }

    if chart_id not in supported:
        raise ValueError(
            "Choose a supported categorical inventory field."
        )

    field, _, dimension = chart_id.partition(".")

    if chart_id == "ai_source_group":
        field = "ai_source"

    fields = {
        item["id"]: item
        for item in snapshot["fields"]
    }

    if chart_id == "ai_source_group":
        options = ["Developed in-house", "Vendor AI"]
    elif dimension:
        options = ["Yes", "No", "Unknown"]
    elif field == "risk_tier":
        options = ["High", "Medium", "Low", "Unknown"]
    else:
        options = fields.get(field, {}).get("options", [])

    title, kind = supported[chart_id]

    return {
        "id": chart_id,
        "title": title,
        "kind": kind,
        "field": field,
        "dimension": dimension,
        "multi": field in config.MULTI,
        "options": options,
    }


def _categories(prepared_record, definition):
    """Apply consistent category and data-quality rules."""

    cells, product, invalid = prepared_record
    field = definition["field"]
    value = product.get(field)

    if not text(cells.get(field)):
        return ["Missing"], "Missing"

    if field in invalid or value is None or value == []:
        return ["Invalid"], "Invalid"

    # Optional grouped source view, using approved normalized categories.
    if definition["id"] == "ai_source_group":
        if value == "Developed in-house":
            return ["Developed in-house"], "valid"

        if isinstance(value, str) and value in config.VENDOR_SOURCES:
            return ["Vendor AI"], "valid"

        return ["Unclassified"], "Unclassified"

    dimension = definition["dimension"]

    if dimension and isinstance(value, dict):
        selections = [value.get(dimension)]
    elif definition["multi"]:
        selections = value
    else:
        selections = [value]

    if (
        not isinstance(selections, list)
        or any(
            item not in definition["options"]
            for item in selections
        )
    ):
        return ["Unclassified"], "Unclassified"

    # A record contributes once per category, even if repeated in its cell.
    return list(dict.fromkeys(selections)), "valid"


def _distribution(definition, prepared):
    counts = Counter()
    quality = Counter()

    for record in prepared:
        selections, classification = _categories(
            record,
            definition,
        )

        quality[classification] += 1

        if classification == "valid":
            counts.update(selections)

    selection_count = sum(counts.values())
    denominator = len(prepared)
    options = definition["options"]

    labels = [
        label
        for label in options
        if counts[label] or definition["field"] == "risk_tier"
    ]

    if not definition["multi"]:
        for label in ["Missing", "Invalid", "Unclassified"]:
            if quality[label]:
                counts[label] = quality[label]
                labels.append(label)

    if definition["kind"] == "bar":
        labels.sort(key=lambda label: (-counts[label], label))

    buckets = []

    for label in labels:
        percentage = (
            round(100 * counts[label] / denominator, 2)
            if denominator
            else 0
        )

        buckets.append({
            "label": label,
            "count": counts[label],
            "percent": percentage,
            "record_percent": percentage,
            "color_index": (
                options.index(label)
                if label in options
                else -1
            ),
        })

    return {
        "id": definition["id"],
        "title": definition["title"],
        "kind": definition["kind"],
        "multi": definition["multi"],
        "total_records": denominator,
        "valid_records": quality["valid"],
        "missing_records": quality["Missing"],
        "invalid_records": quality["Invalid"],
        "unclassified_records": quality["Unclassified"],
        "selection_count": selection_count,
        "denominator": denominator,
        "buckets": buckets,
        "note": (
            SOURCE_GROUP_NOTE
            if definition["id"] == "ai_source_group"
            else ""
        ),
    }


def distributions(snapshot, records):
    prepared = _prepare(records)

    return {
        "total_records": len(records),
        "charts": [
            _distribution(
                _definition(snapshot, chart_id),
                prepared,
            )
            for chart_id, _, _ in CHARTS
        ],
    }


def _comparison_distribution(definition, prepared):
    """Include quality categories and count each source record once per bucket."""
    chart = _distribution(definition, prepared)
    if chart["multi"]:
        for quality in ["Missing", "Invalid", "Unclassified"]:
            count = chart[quality.lower() + "_records"]
            if count:
                percentage = round(100 * count / len(prepared), 2)
                chart["buckets"].append({
                    "label": quality, "count": count, "percent": percentage,
                    "record_percent": percentage, "color_index": -1,
                })
    return chart


def comparison(snapshot, records, group_by, breakdown_by, path=()):
    """Compare two fields within an optional ordered ancestor path."""

    if group_by == breakdown_by:
        raise ValueError(
            "Select two different inventory fields to compare."
        )

    group_definition = _definition(snapshot, group_by)
    breakdown_definition = _definition(snapshot, breakdown_by)

    prepared = _prepare(records)
    ancestors = []
    used = {group_by, breakdown_by}
    if not isinstance(path, (list, tuple)) or len(path) > len(CHARTS) - 2:
        raise ValueError("Choose a supported sequence of inventory fields.")
    for item in path:
        if not isinstance(item, dict) or not isinstance(item.get("field"), str):
            raise ValueError("Choose a supported inventory field for each level.")
        field = item["field"]
        definition = _definition(snapshot, field)
        if field in used or item.get("value") not in [*definition["options"], "Missing", "Invalid", "Unclassified"]:
            raise ValueError("Choose different fields and a valid category for each level.")
        used.add(field)
        ancestors.append({"field": field, "title": definition["title"], "value": item["value"]})
        prepared = [row for row in prepared if item["value"] in _categories(row, definition)[0]]
    members = {}

    for record in prepared:
        labels, _ = _categories(record, group_definition)

        for label in labels:
            members.setdefault(label, []).append(record)

    order = [
        *group_definition["options"],
        "Missing",
        "Invalid",
        "Unclassified",
    ]

    groups = []

    for label in dict.fromkeys(order):
        if label not in members:
            continue

        rows = members[label]
        chart = _comparison_distribution(breakdown_definition, rows)

        chart["title"] = (
            breakdown_definition["title"]
            + " — "
            + group_definition["title"]
            + ": "
            + label
        )

        chart["percent_label"] = "% within group"
        chart["path"] = [*ancestors, {
            "field": group_by, "title": group_definition["title"], "value": label,
        }]
        if ancestors:
            chart["title"] = " / ".join(
                item["title"] + ": " + item["value"] for item in ancestors
            ) + " / " + chart["title"]

        chart["basis"] = (
            str(len(rows))
            + " records in "
            + label
            + " · % within this group"
        )

        groups.append({
            "label": label,
            "count": len(rows),
            "percent": (
                round(100 * len(rows) / len(prepared), 2)
                if prepared
                else 0
            ),
            "chart": chart,
        })

    # This total is independent of overlapping row groups and expanded children.
    summary = _comparison_distribution(breakdown_definition, prepared)
    summary["path"] = ancestors
    return {
        "summary": summary,
        "path": ancestors,
        "group_by": group_by,
        "group_title": group_definition["title"],
        "group_multi": group_definition["multi"],
        "breakdown_by": breakdown_by,
        "breakdown_title": breakdown_definition["title"],
        "breakdown_multi": breakdown_definition["multi"],
        "group_note": (
            SOURCE_GROUP_NOTE
            if group_by == "ai_source_group"
            else ""
        ),
        "total_records": len(prepared),
        "groups": groups,
    }
