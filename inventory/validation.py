"""Pure, deterministic record validation with explicit batch duplicate flags."""
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
import re
from email_validator import validate_email, EmailNotValidError
import inventory as config
from inventory.normalization import normalize, text

@dataclass
class Finding:
    rule_id: str
    severity: str
    source_response_id: str
    source_row: int
    system_name: str
    fields: list
    submitted_value: object
    message: str
    expected_condition: str

    def to_dict(self):
        return asdict(self)


@lru_cache(maxsize=20000)
def email_domain(value):
    try:
        return validate_email(value, check_deliverability=False).domain.lower()
    except EmailNotValidError:
        return None


def placeholder_text(value):
    value = re.sub(r'\s+', ' ', text(value)).casefold().strip(' .!_-')
    return (value in config.PLACEHOLDERS or value.isnumeric() or bool(re.fullmatch(
        r'(?:(?:this is|just|for) (?:a )?)?(?:test(?:ing)?(?:[\s._-]*(?:test|\d+|agent|description|purpose|system|name|data))*)'
        r'|new agent(?:[\s._-]*\d+)?|untitled(?: agent)?|dummy|sample|asdf|abc', value)))


def validate_row(inputs, source_row, as_of, legacy=False, formulas=(), profile='forms'):
    product, problems = normalize(inputs,legacy,formulas)
    findings = []
    bad = {p[0] for p in problems}
    def add(rule, fields, message, expected, severity=None):
        findings.append(Finding(rule,severity or config.RULE_SEVERITIES[rule],text(inputs.get('response_id')),
            source_row,text(inputs.get('system_name')),fields,{config.LABELS.get(f,f):inputs.get(f,'') for f in fields},message,expected))
    for field,message in problems:
        rule = 'ENUM-01'
        if field in config.COUNTS: rule = 'COUNT-01'
        elif field in config.DATES: rule = 'DATE-01'
        elif field == 'impact': rule = 'IMPACT-01'
        elif field == 'risk_tier': rule = 'RISK-01'
        elif field == 'human_oversight': rule = 'HITL-01'
        if field in formulas:
            add('FORMULA-01',[field],'Formula cells cannot be validated as literal values.','Provide the literal value in the source file.')
        elif profile=='agents' and field=='deployment_status' and text(inputs.get(field)).casefold()=='available':
            add('GAP-01',[field],'Available does not establish the inventory lifecycle status.','Supply an explicit deployment status; no Active status is inferred.')
        else:
            add(rule,[field],message,'Use the supported literal value or category for this field.')
    required = config.REQUIRED if profile=='forms' else config.REQUIRED-{'application_id','ai_source','lines_of_business','submitter_name','submitted_date'}
    for field in sorted(required):
        if not text(inputs.get(field)) or (field in config.MULTI and field not in bad and not product[field]):
            add('REQ-01',[field],'This required field is blank.','Provide a value.')
    for field in ['system_name','business_purpose']:
        value = text(inputs.get(field))
        if value and placeholder_text(value):
            add('TEXT-01',[field],'Test-only or placeholder text does not describe this system.','Provide the actual system name or business purpose in the source file.')
    if text(product['application_id']).casefold() in {'not available','unknown'}:
        add('APP-01',['application_id'],'Application ID is unavailable.','Supply the application ID in the source when known.')
    for field in ['business_owner_email','technical_owner_email','submitter_name']:
        if text(inputs.get(field)) and placeholder_text(inputs[field]):
            add('REQ-02',[field],'A placeholder is not an accountable person.','Provide the actual owner or submitter in the source file.')
    for field in ['business_owner_email','technical_owner_email']:
        if profile=='agents': continue
        if field in bad or not product[field]: continue
        domain = email_domain(product[field])
        if domain is None:
            add('EMAIL-01',[field],'Enter exactly one syntactically valid email address.','Use one email, without a display name or list.')
        elif domain not in config.RECOGNIZED_DOMAINS:
            add('EMAIL-02',[field],'Owner email domain is outside the configured recognized domains.','Confirm the address; no directory or DNS verification is performed.')
    vendor = text(product['vendor_owner']).casefold()
    meaningful = vendor not in {'','n/a','unknown','not available','none','tbd','test'}
    source = product['ai_source']
    if 'ai_source' not in bad and 'vendor_owner' not in bad:
        if source in config.OPTIONS['ai_source'][1:5] and not meaningful:
            add('VENDOR-01',['ai_source','vendor_owner'],'This acquisition source requires a meaningful Vendor Owner.','Provide the accountable vendor contact.')
        elif source in {'Other','Unknown'} and not meaningful:
            add('VENDOR-02',['ai_source','vendor_owner'],'Vendor involvement is unresolved.','Confirm the vendor contact if applicable.')
        if source == 'Unknown':
            add('ENUM-01',['ai_source'],'Acquisition source is explicitly Unknown.','Confirm the source when known.',config.UNKNOWN_SEVERITIES['ENUM-01'])
    types = set(product['ai_types'])
    if 'ai_types' not in bad:
        if 'Unknown' in types:
            add('ENUM-01',['ai_types'],'AI technology is explicitly Unknown.','Confirm technology when known.',config.UNKNOWN_SEVERITIES['ENUM-01'])
        for field,explicit,broad,rule in [
            ('llm_count',{'Large Language Model (LLM)'},{'Agentic AI','Generative AI (GenAI)'},'COUNT-02'),
            ('ml_dl_count',{'Machine Learning (ML)','Deep Learning (DL)'},{'Predictive Analytics'},'COUNT-03')]:
            if field in bad: continue
            positive = product[field] is not None and product[field] > 0
            if types & explicit and not positive:
                add(rule,['ai_types',field],'The declared technology requires an actual positive model count.','Correct the technology selection or supply the actual positive count.')
            else:
                broad_applies = bool(types & broad) if field == 'llm_count' else types == {'Predictive Analytics'}
                if broad_applies and not positive:
                    add('COUNT-04',['ai_types',field],'This broader technology label may involve models; the count is unresolved.','Confirm the model type and count; a positive count is not universally required.')
                if product[field+'_state'] == 'unknown':
                    add('COUNT-06',[field],'Count is explicitly Unknown.','Supply the actual count when known.')
            if positive and not types & (explicit | broad):
                add('COUNT-05',['ai_types',field],'A positive count has no corresponding declared technology.','Confirm both the technology and count.')
    for field in sorted(config.DATES):
        if field in bad: continue
        value = product[field]
        if field == 'submitted_date' and profile=='forms' and (not value or date.fromisoformat(value) > as_of):
            add('DATE-01',[field],'Date Submitted must be present and not future.','Enter a date on or before '+as_of.isoformat()+'.')
        if field == 'go_live_date' and 'deployment_status' not in bad:
            future = value and date.fromisoformat(value) > as_of
            if product['deployment_status'] == 'Active' and (not value or future):
                add('DATE-02',['deployment_status',field],'Active products require a nonfuture Go-Live Date.','Enter the actual go-live date on or before '+as_of.isoformat()+'.')
            elif product['deployment_status'] and future:
                add('DATE-03',['deployment_status',field],'This future Go-Live Date appears planned rather than actual.','Confirm that the planned date is intended.')
    for field,exclusive in [('lines_of_business',{'None'}),('states',{'None','All States'})]:
        if field not in bad and len(product[field]) > 1 and set(product[field]) & exclusive:
            add('SCOPE-01',[field],'An exclusive selection is combined with another selection.','Select None/All States alone, or select concrete categories.')
    if not {'lines_of_business','states'} & bad and 'Medicaid' in product['lines_of_business'] and (not product['states'] or 'None' in product['states']):
        add('SCOPE-02',['lines_of_business','states'],'Medicaid requires a jurisdiction.','Select at least one state, District of Columbia, or All States.')
    if product['impact'] and 'Unknown' in product['impact'].values():
        add('IMPACT-01',['impact'],'One or more impact dimensions are Unknown.','Confirm impact when known; Unknown is not No.',config.UNKNOWN_SEVERITIES['IMPACT-01'])
    if product['risk_tier'] == 'Unknown':
        add('RISK-01',['risk_tier'],'Risk tier is Unknown.','Confirm the risk tier when known.',config.UNKNOWN_SEVERITIES['RISK-01'])
    if product['human_oversight'] == 'Unknown':
        add('HITL-01',['human_oversight'],'Human oversight is Unknown.','Confirm oversight when known.',config.UNKNOWN_SEVERITIES['HITL-01'])
    return product,findings


def validate_upload(parsed, as_of):
    """Immutable per-record results. Cross-record flags affect only matching rows."""
    agents = parsed.profile == 'agents'
    labels = config.AGENT_LABELS if agents else {'response_id':'Response ID', **config.LABELS}
    field_ids = list(config.AGENT_HEADERS.values()) + list(config.AGENT_OPTIONAL.values()) if agents else ['response_id', *config.FIELDS.values()]
    headers = parsed.headers if agents else {('response_id' if q=='ID' else config.FIELDS[q]):h for q,h in parsed.headers.items()}
    field_defs = [{'id':f,'label':labels[f], 'source':headers.get(f), 'rules':config.field_rules(f,parsed.profile),
                   'options':config.OPTIONS.get(f,[])} for f in field_ids]
    extras={f'extra_{i}':header for i,header in enumerate(parsed.extra_headers)}
    field_defs.extend({'id':fid,'label':header or 'Unnamed source column','source':header,
                       'rules':'Retained source metadata; no validation rule is configured.','options':[]} for fid,header in extras.items())
    results=[]
    for index,row in enumerate(parsed.rows):
        if agents:
            inputs={f:row['values'].get(f,'') for f in field_ids}
            formulas=row['formulas']
        else:
            from inventory.normalization import raw_inputs
            inputs=raw_inputs(row)
            formulas=[config.FIELDS.get(q,'response_id') for q in row['formulas']]
        legacy = not agents and 'Override Capability' not in parsed.headers['Q21']
        product, findings=validate_row(inputs,row['source_row'],as_of,legacy,formulas,parsed.profile)
        def add(rule, fields, message, expected):
            findings.append(Finding(rule,config.RULE_SEVERITIES[rule],text(inputs.get('response_id')),
                row['source_row'],text(inputs.get('system_name')),fields,
                {labels.get(f,f):inputs.get(f,'') for f in fields},message,expected))
        if agents:
            for field in ['ai_source','lines_of_business','go_live_date']:
                if not text(inputs.get(field)):
                    add('GAP-01',[field],'The export does not supply this inventory value.',
                        'Provide authoritative metadata; organization details and creation dates are not substitutes.')
            if not text(inputs.get('ai_source')) and text(inputs.get('vendor_owner')).casefold() in config.PLACEHOLDERS:
                add('VENDOR-02',['vendor_owner','ai_source'],'Vendor applicability cannot be verified from this export.',
                    'Provide the acquisition source and a vendor contact or explicit non-applicability.')
            for field in ['market','organization_lob','department','job_title','instructions']:
                if text(inputs.get(field)).casefold() in config.PLACEHOLDERS:
                    add('META-01',[field],'Source metadata is missing or a placeholder.','Supply the metadata in the source export.')
            if text(inputs.get('platform')).casefold() in config.PLACEHOLDERS:
                add('REQ-02',['platform'],'Source platform is missing or a placeholder.','Supply the platform name.')
            if len(str(inputs.get('instructions',''))) == 8000:
                add('LENGTH-01',['instructions'],'Instructions reach the observed 8,000-character boundary.',
                    'Check the source for truncation; length alone does not prove text is incomplete.')
            timestamps={}
            for field in ['created_date','modified_date']:
                value=inputs.get(field,'')
                if isinstance(value,dict): value=value.get('__excel_date__','')
                try:
                    stamp=datetime.fromisoformat(text(value).replace('Z','+00:00'))
                    if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
                    stamp=stamp.astimezone(timezone.utc)
                    if stamp.date()>as_of: raise ValueError('future')
                    timestamps[field]=stamp
                except (ValueError,TypeError):
                    add('DATE-01',[field],'Source date is missing, invalid, or in the future.','Provide a valid ISO date or timestamp on or before '+as_of.isoformat()+'.')
            if len(timestamps)==2 and timestamps['modified_date']<timestamps['created_date']:
                add('DATE-04',['created_date','modified_date'],'Last Modified precedes Date created.','Verify both source timestamps.')
        # Extra raw fields need explicit formula findings too.
        for field in formulas:
            if not any(f.rule_id=='FORMULA-01' and field in f.fields for f in findings):
                add('FORMULA-01',[field],'Formula cells cannot be validated as literal values.','Replace with a literal value in the source file.')
        source_values={parsed.headers[q]:v for q,v in row['values'].items()}
        source_values.update(row['metadata'])
        inputs.update({fid:row['metadata'].get(header,'') for fid,header in extras.items()})
        results.append({'key':index,'source_row':row['source_row'],'response_id':text(inputs.get('response_id')),
            'name':text(inputs.get('system_name')),'owner':text(inputs.get('business_owner_email')),
            'cells':inputs,'source_values':source_values,'findings':[f.to_dict() for f in findings]})
    groups={f:defaultdict(list) for f in ['response_id','system_name','application_id']}
    for r in results:
        for field,group in groups.items():
            value=' '.join(text(r['cells'].get(field)).casefold().split())
            if value and value not in config.PLACEHOLDERS: group[value].append(r['key'])
    for r in results:
        for field,rule in [('response_id','ID-01'),('application_id','ID-02'),('system_name','NAME-01')]:
            value=' '.join(text(r['cells'].get(field)).casefold().split())
            duplicates=groups[field].get(value,[])
            missing=field=='response_id' and (not value or value in config.PLACEHOLDERS)
            if missing or len(duplicates)>1:
                r['findings'].append(Finding(rule,config.RULE_SEVERITIES[rule],r['response_id'],r['source_row'],r['name'],
                    [field],{labels.get(field,field):r['cells'].get(field,'')},
                    'Record ID is missing or a placeholder.' if missing else 'Value is repeated in this upload.',
                    'Provide a stable source ID.' if missing else 'Review the matching source rows: '+', '.join(str(results[i]['source_row']) for i in duplicates[:20])+(' and '+str(len(duplicates)-20)+' more' if len(duplicates)>20 else '')+'.').to_dict())
        r['errors']=sum(f['severity']=='ERROR' for f in r['findings'])
        r['warnings']=sum(f['severity']=='WARNING' for f in r['findings'])
        r['status']='Failed' if r['errors'] else 'Needs review' if r['warnings'] else 'Passed'
        r['affected_fields']=list(dict.fromkeys(field for f in r['findings'] for field in f['fields']))
        for finding in r['findings']:
            finding['title']=config.RULE_TITLES.get(finding['rule_id'],finding['rule_id'])
    return {'profile':parsed.profile,'fields':field_defs,'records':results,'as_of':as_of.isoformat(),
            'rules_version':config.RULES_VERSION,'source_columns':list(results[0]['source_values'])}
