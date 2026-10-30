"""Chart summaries with membership from the existing category rules."""

from inventory.analytics import (
    CHARTS,
    _prepare,
    _definition,
    _categories,
    distributions as base_distributions,
    comparison,
    inventory_error_count,
)


def distributions(snapshot, records):
    result = base_distributions(snapshot, records)

    definitions = [
        _definition(snapshot, identifier)
        for identifier, _, _ in CHARTS
    ]

    result["underlying_records"] = [
        {
            "key": record["key"],
            "name": record["name"],
            "application_id": record["application_id"],
            "source_row": record["source_row"],
            "status": record["status"],
            "owners": {
                field: record["cells"].get(field, "")
                for field in ("business_owner_email", "technical_owner_email", "vendor_owner")
            },
            "findings": [
                {
                    **{field: issue[field] for field in ("rule_id", "title", "fields", "message", "fix", "requirement")},
                    "values": {field: record["cells"].get(field, "") for field in issue["fields"]},
                }
                for issue in record["findings"]
            ],
            "categories": {
                definition["id"]: _categories(
                    prepared, definition
                )[0]
                for definition in definitions
            },
        }
        for record, prepared in zip(records, _prepare(records))
    ]

    return result
