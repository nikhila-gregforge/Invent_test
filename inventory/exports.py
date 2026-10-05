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
        raise ValueError('Unknown inventory field filter.')
    status = args.get('status','attention')
    if status not in {'all','attention','Passed','Needs review','Failed'}:
        raise ValueError('Unknown status filter.')
    search = args.get('q','').strip().casefold()
    result = []
    for r in snapshot['records']:
        if status=='attention' and r['status']=='Passed':
            continue
        if status not in {'all','attention'} and r['status']!=status:
            continue
        if search and not any(search in display(v).casefold() for v in [r['name'],r['response_id'],r['owner'],r['cells'].get('application_id')]):
            continue
        if args.get('field') and not any(args['field'] in f['fields'] for f in r['findings']):
            continue
        result.append(r)
    return sorted(result,key=lambda r:(-r['errors'],-r['warnings'],r['source_row']))


def export_report(snapshot, records, kind):
    run = snapshot['run']
    fields = snapshot['fields']
    prefix = ['Validation run','Source file','Worksheet','Rules version','Validated as of','Mapping fingerprint']
    context = [run['id'],run['filename'],run['sheet'],run['rules_version'],run['as_of'],run.get('mapping_hash','legacy')]
    if kind=='records':
        columns = snapshot['source_columns']
        mapping = {f['label']:f.get('source') for f in fields}
        return csv_bytes(prefix+['Source row','Record ID','Validation status','Errors','Warnings','Checks not run','Confirmed mapping']+['Source: '+c for c in columns],
            (context+[r['source_row'],r['response_id'],r['status'],r['errors'],r['warnings'],
             [c['reason'] for c in r.get('not_checked',[])],mapping]+[r['source_values'].get(c,'') for c in columns] for r in records))
    if kind=='issues':
        by_id = {f['id']:f for f in fields}
        return csv_bytes(prefix+['Source row','Record ID','System name','Severity','Rule ID','Rule','Inventory fields',
            'Source columns','Submitted values','What happened','Requirement','Why this severity','What to change in the source'],
            (context+[r['source_row'],r['response_id'],r['name'],f['severity'],f['rule_id'],f['title'],
             '; '.join(by_id[v]['label'] for v in f['fields']),
             {by_id[v]['label']:by_id[v].get('source') for v in f['fields']},
             {by_id[v]['label']:r['cells'].get(v,'') for v in f['fields']},f['message'],f.get('requirement',''),
             f.get('why',f['message']),f['expected_condition']] for r in records for f in r['findings']))
    raise ValueError('Choose an issues report or a records report.')
