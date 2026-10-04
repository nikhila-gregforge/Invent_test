"""Shared query logic for the interface and CSV reports."""
from collections import Counter
from io import StringIO
import csv
import json
import unicodedata


def display(value):
    if isinstance(value,dict):
        if '__excel_date__' in value: return value['__excel_date__']
        return json.dumps(value,ensure_ascii=False)
    if isinstance(value,list): return '; '.join(str(v) for v in value)
    return '' if value is None else str(value)


def safe_cell(value):
    value=display(value)
    probe=value.lstrip()
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]).startswith('C')): probe=probe[1:]
    return "'"+value if probe.startswith(('=','+','-','@')) else value


def csv_bytes(headers, rows):
    output=StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow([safe_cell(h) for h in headers])
    for row in rows: writer.writerow([safe_cell(v) for v in row])
    return output.getvalue().encode('utf-8-sig')


def select_records(snapshot, args):
    fields={f['id'] for f in snapshot['fields']}
    for key in ['field','column']:
        if args.get(key) and args[key] not in fields: raise ValueError('Unknown field filter.')
    status=args.get('status','attention')
    if status not in {'all','attention','Passed','Needs review','Failed'}: raise ValueError('Unknown status filter.')
    severity=args.get('severity','')
    if severity not in {'','ERROR','WARNING'}: raise ValueError('Unknown severity filter.')
    rule=args.get('rule','')
    if rule and rule not in {f['rule_id'] for r in snapshot['records'] for f in r['findings']}:
        raise ValueError('Unknown rule filter for this run.')
    column=args.get('column','')
    if (args.get('value') or args.get('blank')=='1') and not column: raise ValueError('Select a column for the value filter.')
    search=args.get('q','').strip().casefold()
    result=[]
    for r in snapshot['records']:
        if status=='attention' and r['status']=='Passed': continue
        if status not in {'all','attention'} and r['status']!=status: continue
        if search and not any(search in display(v).casefold() for v in [r['name'],r['response_id'],r['owner'],r['cells'].get('application_id')]): continue
        if args.get('field') or rule or severity:
            if not any((not args.get('field') or args['field'] in f['fields']) and
                       (not rule or f['rule_id']==rule) and (not severity or f['severity']==severity) for f in r['findings']): continue
        if column:
            cell=display(r['cells'].get(column)).strip().casefold()
            value=args.get('value','').strip().casefold()
            if args.get('blank')=='1' and cell: continue
            if value and (cell!=value if args.get('exact')=='1' else value not in cell): continue
        result.append(r)
    sort=args.get('sort','issues')
    keys={'issues':lambda r:(r['errors'],r['warnings'],-r['source_row']),
          'name':lambda r:(r['name'].casefold(),r['source_row']),
          'id':lambda r:(r['response_id'].casefold(),r['source_row']),
          'source_row':lambda r:r['source_row']}
    if sort not in keys: raise ValueError('Unknown sort order.')
    return sorted(result,key=keys[sort],reverse=sort=='issues')


def field_summary(snapshot, records):
    summary=[]
    for field in snapshot['fields']:
        fid=field['id']
        affected=errors=warnings=blank=0
        values=Counter()
        for r in records:
            value=display(r['cells'].get(fid)).strip()
            blank+=not bool(value)
            if value: values[value]+=1
            findings=[f for f in r['findings'] if fid in f['fields']]
            affected+=bool(findings)
            errors+=any(f['severity']=='ERROR' for f in findings)
            warnings+=any(f['severity']=='WARNING' for f in findings)
        summary.append({**field,'total':len(records),'affected':affected,'errors':errors,'warnings':warnings,
                        'blank':blank,'distinct':len(values),
                        'common':[{'value':value,'count':count} for value,count in values.most_common(8)]})
    return summary


def export_report(snapshot, records, kind):
    run=snapshot['run']
    prefix=['Validation run','Rules version','Validated as of']
    context=[run['id'],run['rules_version'],run['as_of']]
    if kind=='records':
        columns=snapshot['source_columns']
        return csv_bytes(prefix+['Source row','Record ID','Validation status','Errors','Warnings']+columns,
            (context+[r['source_row'],r['response_id'],r['status'],r['errors'],r['warnings']]+[r['source_values'].get(c,'') for c in columns] for r in records))
    if kind=='issues':
        labels={f['id']:f['label'] for f in snapshot['fields']}
        return csv_bytes(prefix+['Source row','Record ID','System name','Severity','Rule ID','Rule','Fields','Submitted values','Problem','Expected condition'],
            (context+[r['source_row'],r['response_id'],r['name'],f['severity'],f['rule_id'],f['title'],
             '; '.join(labels.get(v,v) for v in f['fields']),{labels.get(v,v):r['cells'].get(v,'') for v in f['fields']},f['message'],f['expected_condition']]
             for r in records for f in r['findings']))
    if kind=='fields':
        return csv_bytes(prefix+['Field','Source column','Records','Affected records','Records with errors','Records with warnings','Blank','Distinct values','Rules'],
            (context+[f['label'],f['source'],f['total'],f['affected'],f['errors'],f['warnings'],f['blank'],f['distinct'],f['rules']] for f in field_summary(snapshot,records)))
    raise ValueError('Unknown report type.')
