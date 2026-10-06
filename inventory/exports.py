"""Shared record selection and spreadsheet-safe reports with source traceability."""
from io import StringIO
import csv
import json
import unicodedata


def display(value):
    if isinstance(value,dict):
        return value.get('__excel_date__',value.get('__excel_time__',json.dumps(value,ensure_ascii=False)))
    if isinstance(value,list):
        return '; '.join(str(v) for v in value)
    return '' if value is None else str(value)


def safe_cell(value):
    value = display(value)
    probe = value.lstrip()
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]).startswith('C')):
        probe = probe[1:]
    return "'"+value if probe.startswith(('=','+','-','@')) else value


def csv_bytes(headers, rows):
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([safe_cell(h) for h in headers])
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return output.getvalue().encode('utf-8-sig')


def select_records(snapshot, args):
    fields = {f['id'] for f in snapshot['fields']}
    if args.get('field') and args['field'] not in fields:
        raise ValueError('Choose an inventory field from the filter list.')
    status = args.get('status','Errors')
    if status not in {'all','Passed','Errors'}:
        raise ValueError('Choose All records, Errors or Passed.')
    search = args.get('q','').strip().casefold()
    result = []
    for record in snapshot['records']:
        if status!='all' and record['status']!=status:
            continue
        if search and not any(search in display(v).casefold() for v in [record['name'],record['application_id'],record['owner']]):
            continue
        if args.get('field') and not any(args['field'] in f['fields'] for f in record['findings']):
            continue
        result.append(record)
    return sorted(result,key=lambda r:(-r['errors'],r['source_row']))


def export_report(snapshot, records, kind):
    run = snapshot['run']
    prefix = ['Validation run','Source file','Worksheet','Inventory format','Rules version','Validated as of']
    context = [run['id'],run['filename'],run['sheet'],run['schema_version'],run['rules_version'],run['as_of']]
    if kind=='records':
        columns = snapshot['source_columns']
        return csv_bytes(prefix+['Source row','Validation status','Error count','Checks blocked by errors']+['Source: '+c for c in columns],
            (context+[r['source_row'],r['status'],r['errors'],[c['reason'] for c in r['not_checked']]]+
             [r['source_values'][c] for c in columns] for r in records))
    if kind=='errors':
        labels = {f['id']:f['label'] for f in snapshot['fields']}
        return csv_bytes(prefix+['Source row','Application / System ID','System name','Rule ID','Error',
            'Inventory fields','Submitted values','Problem','How to fix','Requirement'],
            (context+[r['source_row'],r['application_id'],r['name'],f['rule_id'],f['title'],
             '; '.join(labels[v] for v in f['fields']),{labels[v]:r['cells'][v] for v in f['fields']},
             f['message'],f['fix'],f['requirement']] for r in records for f in r['findings']))
    raise ValueError('Choose an errors report or a records report.')
