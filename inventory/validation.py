"""One rule catalogue supplies execution, explanations, field help and reports."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date
from functools import lru_cache
import re
from email_validator import validate_email, EmailNotValidError
import inventory as config
from inventory.normalization import normalize, text

RULES = []


def rule(identifier, title, severity, fields, requirement, why, action, depends=()):
    def register(check):
        RULES.append(dict(id=identifier,title=title,severity=severity,fields=list(fields),
                          requirement=requirement,why=why,action=action,depends=list(depends),check=check))
        return check
    return register


@dataclass
class Finding:
    rule_id: str
    severity: str
    source_response_id: str
    source_row: int
    system_name: str
    fields: list
    submitted_value: dict
    message: str
    expected_condition: str
    title: str
    requirement: str
    why: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Context:
    inputs: dict
    product: dict
    problems: dict
    formulas: set
    source_row: int
    as_of: date
    groups: dict = dc_field(default_factory=dict)
    missing_columns: set = dc_field(default_factory=set)
    not_checked: list = dc_field(default_factory=list)
    current: dict = dc_field(default_factory=dict)

    def invalid(self, *fields):
        blocked = [f for f in fields if f in self.problems or f in self.formulas]
        if blocked:
            self.skip(blocked)
        return bool(blocked)

    def skip(self, fields):
        item = {'rule_id':self.current['id'],'title':self.current['title'],
                'fields':self.current['fields'],
                'reason':'Cannot check this requirement until '+', '.join(config.LABELS[f] for f in fields)+' has a valid value.'}
        if item not in self.not_checked:
            self.not_checked.append(item)


@lru_cache(maxsize=20000)
def email_domain(value):
    try:
        return validate_email(value,check_deliverability=False).domain.lower()
    except EmailNotValidError:
        return None


def placeholder_text(value):
    value = re.sub(r'\s+',' ',text(value)).casefold().strip(' .!_-')
    return value in config.PLACEHOLDERS or value.isnumeric() or bool(re.fullmatch(
        r'(?:(?:this is|just|for) (?:a )?)?(?:test(?:ing)?(?:[\s._-]*(?:test|\d+|agent|description|purpose|system|name|data))*)'
        r'|new agent(?:[\s._-]*\d+)?|untitled(?: agent)?|dummy|sample|asdf|abc',value))


@rule('REQ-01','Required inventory value','ERROR',sorted(config.REQUIRED),
      'Every required inventory field must have a value.',
      'A required part of the inventory record is missing.',
      'Add the missing value in the source file and upload it again.')
def required(c):
    for f in sorted(config.REQUIRED):
        if f in c.missing_columns:
            yield [f], 'No source column was provided for '+config.LABELS[f]+'.'
        elif not text(c.inputs.get(f)) or (f in config.MULTI and f not in c.problems and not c.product[f]):
            yield [f], config.LABELS[f]+' is blank in this record.'


@rule('FORMULA-01','Provide a literal value','ERROR',config.INVENTORY_FIELDS,
      'Mapped inventory cells must contain values rather than Excel formulas.',
      'The app cannot establish the submitted value without evaluating a formula.',
      'Replace the formula with its actual value in the source file.')
def formulas(c):
    for f in sorted(c.formulas):
        yield [f], 'This cell contains an Excel formula.'


def format_rule(identifier, title, fields, requirement, why, action):
    @rule(identifier,title,'ERROR',fields,requirement,why,action)
    def check(c):
        for f in fields:
            if f in c.problems and f not in c.formulas:
                yield [f], config.LABELS[f]+': '+c.problems[f]


format_rule('COUNT-01','Model count must be a whole number',sorted(config.COUNTS),
            'Use 0 or a whole number above 0. Unknown is accepted for review; optional counts may be blank.',
            'A model name, response mode, negative number or fraction does not give a valid count.',
            'Enter the actual number of models, such as 0, 1 or 2. Keep Unknown only when the count needs confirmation.')
format_rule('DATE-01','Use a valid date',sorted(config.DATES),
            'Use YYYY-MM-DD, M/D/YYYY, M/D/YY, or an Excel date cell. Slash dates use month/day order.',
            'The submitted value cannot be interpreted as a valid date in the supported formats.',
            'Correct the date in the source file, preferably using YYYY-MM-DD.')
format_rule('ENUM-01','Use an accepted choice',list(config.OPTIONS),
            'Use the accepted choices for this field. Separate multiple choices with semicolons. Other requires a description.',
            'The submitted value does not meet the inventory field’s choice or selection requirements.',
            'Choose an accepted value shown in the field rules. For Other, write Other: followed by a description.')
format_rule('IMPACT-01','Provide all three impact dimensions',['impact'],
            'Supply Member, Regulatory and Financial exactly once each, using Yes, No or Unknown.',
            'The impact profile cannot be interpreted consistently without all three dimensions.',
            'Use a complete profile, for example Member: No; Regulatory: No; Financial: Yes.')


@rule('TEXT-01','Use the actual name or purpose','ERROR',['system_name','business_purpose'],
      'Provide the real system name and a meaningful description of its purpose.',
      'Test-only text, generic placeholders and numbers alone do not identify the system or explain its use.',
      'Replace the placeholder with the actual system name or a description of what it does and why it is used.')
def purpose(c):
    for f in ['system_name','business_purpose']:
        if f not in c.formulas and text(c.inputs.get(f)) and placeholder_text(c.inputs[f]):
            yield [f], config.LABELS[f]+' contains test-only or placeholder text.'


@rule('APP-01','Confirm the application ID','WARNING',['application_id'],
      'Provide the application ID. Not Available and Unknown are accepted while the ID is unresolved.',
      'The placeholder is allowed, but the system cannot yet be linked to a confirmed application ID.',
      'Confirm the application ID and update the source when it is available.')
def application(c):
    if text(c.product['application_id']).casefold() in {'not available','unknown'}:
        yield ['application_id'], 'The application ID is not yet available.'


PEOPLE = ['business_owner_email','technical_owner_email','submitter_name']
OWNERS = PEOPLE[:2]


@rule('REQ-02','Identify an accountable person','ERROR',PEOPLE,
      'An owner may be a meaningful name or one valid email. The submitter must have a meaningful name.',
      'A placeholder or a value with no letters does not identify an accountable person.',
      'Enter the person’s name, with role or department if useful, or enter one valid owner email.')
def people(c):
    for f in PEOPLE:
        value = text(c.inputs.get(f))
        if f not in c.formulas and value and (placeholder_text(value) or not any(ch.isalpha() for ch in value)):
            yield [f], config.LABELS[f]+' does not identify a person.'


@rule('EMAIL-01','Use a valid owner email','ERROR',OWNERS,
      'When an owner value contains @, it must be exactly one valid email address. A person’s name is also accepted.',
      'The value looks like an email address but does not have a valid email format.',
      'Correct the email address, or provide the owner’s name instead.')
def owner_email(c):
    for f in OWNERS:
        value = text(c.inputs.get(f))
        if f not in c.formulas and '@' in value and email_domain(value) is None:
            yield [f], 'The email entered for '+config.LABELS[f]+' has an invalid format.'


@rule('EMAIL-02','Confirm an external owner email','WARNING',OWNERS,
      'Owner names and valid emails are accepted. Email domains outside centene.com require confirmation.',
      'The email format is valid, but the address is outside the configured Centene domain.',
      'Confirm that this external address belongs to the accountable owner. No directory lookup is performed.')
def owner_domain(c):
    for f in OWNERS:
        value = text(c.inputs.get(f))
        domain = email_domain(value) if '@' in value and f not in c.formulas else None
        if domain and domain not in config.RECOGNIZED_DOMAINS:
            yield [f], 'The owner email uses the external domain '+domain+'.'


@rule('VENDOR-01','Provide the vendor contact','ERROR',['ai_source','vendor_owner'],
      'Vendor-built, licensed, off-the-shelf and hybrid systems require an accountable vendor contact.',
      'The selected acquisition source involves a vendor, but no meaningful vendor contact is supplied.',
      'Add the vendor and accountable contact in Vendor Owner.',depends=['ai_source'])
def vendor(c):
    if c.product['ai_source'] in config.OPTIONS['ai_source'][1:5] and not c.invalid('vendor_owner') and placeholder_text(c.inputs.get('vendor_owner')):
        yield ['ai_source','vendor_owner'], 'The selected acquisition source requires a vendor contact.'


@rule('VENDOR-02','Confirm whether a vendor is involved','WARNING',['ai_source','vendor_owner'],
      'When acquisition is Other or Unknown, confirm whether a vendor contact is needed.',
      'Vendor involvement cannot be determined from the acquisition value and missing contact.',
      'Confirm the acquisition source and supply the vendor contact when applicable.',depends=['ai_source'])
def vendor_unknown(c):
    if c.product['ai_source'] in {'Other','Unknown'} and not c.invalid('vendor_owner') and placeholder_text(c.inputs.get('vendor_owner')):
        yield ['ai_source','vendor_owner'], 'Vendor involvement is unresolved.'


MODEL_TYPES = [('llm_count',{'Large Language Model (LLM)'},{'Agentic AI','Generative AI (GenAI)'}),
               ('ml_dl_count',{'Machine Learning (ML)','Deep Learning (DL)'},{'Predictive Analytics'})]


@rule('COUNT-02','Count the declared language models','ERROR',['ai_types','llm_count'],
      'If Types of AI Used includes Large Language Model (LLM), LLM Count must be greater than 0.',
      'The system declares an LLM, but its count does not confirm that at least one LLM is used.',
      'Provide the actual positive LLM count, or correct the technology selection in the source.',depends=['ai_types'])
def llm_count(c):
    if MODEL_TYPES[0][1] & set(c.product['ai_types']) and not c.invalid('llm_count') and not (c.product['llm_count'] or 0)>0:
        yield ['ai_types','llm_count'], 'LLM is selected, but LLM Count is '+(text(c.inputs.get('llm_count')) or 'blank')+'.'


@rule('COUNT-03','Count the declared ML or DL models','ERROR',['ai_types','ml_dl_count'],
      'If Machine Learning or Deep Learning is selected, ML/DL Models Count must be greater than 0.',
      'The system declares ML or DL, but its count does not confirm that at least one such model is used.',
      'Provide the actual positive ML/DL count, or correct the technology selection in the source.',depends=['ai_types'])
def ml_count(c):
    if MODEL_TYPES[1][1] & set(c.product['ai_types']) and not c.invalid('ml_dl_count') and not (c.product['ml_dl_count'] or 0)>0:
        yield ['ai_types','ml_dl_count'], 'ML or DL is selected, but ML/DL Models Count is '+(text(c.inputs.get('ml_dl_count')) or 'blank')+'.'


@rule('COUNT-04','Confirm models behind a broad technology label','WARNING',['ai_types','llm_count','ml_dl_count'],
      'Agentic AI, GenAI and Predictive Analytics may use models; confirm a blank, unknown or zero count.',
      'A broad technology label does not prove which model type is present, so this is a request for confirmation.',
      'Confirm the model types and counts. A positive count is not assumed for every broad technology label.',depends=['ai_types'])
def broad_count(c):
    types = set(c.product['ai_types'])
    for f,explicit,broad in MODEL_TYPES:
        if not types & explicit and types & broad and not c.invalid(f) and not (c.product[f] or 0)>0:
            yield ['ai_types',f], config.LABELS[f]+' needs confirmation for the selected technology.'


@rule('COUNT-05','Confirm the count and technology together','WARNING',['ai_types','llm_count','ml_dl_count'],
      'A positive model count should have a corresponding technology selection.',
      'The count and technology may be inconsistent, but either value could need clarification.',
      'Review the technology selection and model count together.',depends=['ai_types'])
def count_mismatch(c):
    for f,explicit,broad in MODEL_TYPES:
        if not c.invalid(f) and (c.product[f] or 0)>0 and not set(c.product['ai_types']) & (explicit|broad):
            yield ['ai_types',f], 'A positive '+config.LABELS[f]+' has no corresponding technology selection.'


@rule('COUNT-06','Confirm an unknown model count','WARNING',sorted(config.COUNTS),
      'Unknown, TBD and Not Available leave a model count unresolved.',
      'Unknown is allowed for review, but does not establish how many models are used.',
      'Obtain the actual count and update the source file.')
def count_unknown(c):
    for f,explicit,broad in MODEL_TYPES:
        # A mandatory positive count is already an error; do not repeat it as a warning.
        if f not in c.problems and c.product[f+'_state']=='unknown' and not set(c.product['ai_types']) & (explicit|broad):
            yield [f], config.LABELS[f]+' is unknown.'


@rule('DATE-05','Submission date cannot be in the future','ERROR',['submitted_date'],
      'Date Submitted must be on or before the saved validation date.',
      'A future date cannot describe when this information was already submitted.',
      'Enter the actual submission date.')
def submitted_date(c):
    value = c.product['submitted_date']
    if 'submitted_date' not in c.problems and value and date.fromisoformat(value)>c.as_of:
        yield ['submitted_date'], 'Date Submitted is later than '+c.as_of.isoformat()+'.'


@rule('DATE-02','Provide the actual go-live date','ERROR',['deployment_status','go_live_date'],
      'An Active system must have a valid go-live date on or before the validation date.',
      'Active means the system is already in use, so its actual go-live date must be known and not future.',
      'Enter the actual go-live date, or correct the deployment status.',depends=['deployment_status'])
def active_date(c):
    if c.product['deployment_status']=='Active' and not c.invalid('go_live_date'):
        value = c.product['go_live_date']
        if not value or date.fromisoformat(value)>c.as_of:
            yield ['deployment_status','go_live_date'], 'The system is Active, but the go-live date is missing or later than '+c.as_of.isoformat()+'.'


@rule('DATE-03','Confirm a planned go-live date','WARNING',['deployment_status','go_live_date'],
      'A future date for a system that is not Active needs confirmation as a planned date.',
      'The date may be intentional, but it does not yet describe an actual go-live.',
      'Confirm that the source is intentionally recording a planned date.',depends=['deployment_status'])
def future_date(c):
    value = c.product['go_live_date']
    if c.product['deployment_status']!='Active' and not c.invalid('go_live_date') and value and date.fromisoformat(value)>c.as_of:
        yield ['deployment_status','go_live_date'], 'The go-live date is in the future.'


@rule('SCOPE-01','Use exclusive scope choices on their own','ERROR',['lines_of_business','states'],
      'None must stand alone. All States must stand alone.',
      'The selected scope values contradict each other.',
      'Keep the exclusive choice alone, or select the concrete lines of business or states.')
def exclusive_scope(c):
    for f,exclusive in [('lines_of_business',{'None'}),('states',{'None','All States'})]:
        if f not in c.problems and len(c.product[f])>1 and set(c.product[f]) & exclusive:
            yield [f], config.LABELS[f]+' combines an exclusive choice with another selection.'


@rule('SCOPE-02','Identify the Medicaid jurisdiction','ERROR',['lines_of_business','states'],
      'Medicaid use requires at least one state, District of Columbia or All States.',
      'Medicaid is selected, but the inventory does not identify where it is used.',
      'Select the actual Medicaid jurisdiction in State.',depends=['lines_of_business'])
def medicaid(c):
    if 'Medicaid' in c.product['lines_of_business'] and not c.invalid('states') and 'None' in c.product['states']:
        yield ['lines_of_business','states'], 'Medicaid is selected with State set to None.'
    # A blank required State already has a required-value error.
    elif 'Medicaid' in c.product['lines_of_business'] and not c.product['states']:
        c.skip(['states'])


@rule('UNKNOWN-01','Confirm an unresolved inventory value','WARNING',['ai_source','ai_types','impact','risk_tier','human_oversight'],
      'Unknown is accepted for review in these fields, but it is not a confirmed classification.',
      'The value is permitted, but a governance detail still needs confirmation.',
      'Confirm the actual classification and update the source when known.')
def unknown(c):
    for f in ['ai_source','ai_types','impact','risk_tier','human_oversight']:
        if f in c.problems:
            continue
        value = c.product[f]
        unknown_value = ('Unknown' in value.values() if isinstance(value,dict) else
                         'Unknown' in value if isinstance(value,list) else value=='Unknown')
        if unknown_value:
            yield [f], config.LABELS[f]+' includes Unknown.'


def duplicate_rule(identifier, f, severity, why):
    @rule(identifier,'Review repeated '+config.LABELS[f].lower(),severity,[f],
          'Application IDs and supplied source record IDs must be unique. Repeated system names require review.',
          why,'Check the source rows and correct an unintended duplicate. Keep distinct records traceable.')
    def check(c):
        value = ' '.join(text(c.inputs.get(f)).casefold().split())
        rows = c.groups.get(f,{}).get(value,[])
        if len(rows)>1 and f not in c.formulas:
            detail = ', '.join(map(str,rows[:20])) + (f' and {len(rows)-20} more' if len(rows)>20 else '')
            yield [f], 'This value appears in source rows '+detail+'.'


duplicate_rule('ID-01','response_id','ERROR','The supplied record ID is shared by multiple rows and cannot uniquely identify a source record.')
duplicate_rule('ID-02','application_id','ERROR','The application ID is repeated, so these rows cannot be distinguished by their inventory identifier.')
duplicate_rule('NAME-01','system_name','WARNING','Different systems may share a name, but a repeated name can also indicate a duplicate entry.')


def catalogue(mapping=None):
    fields = []
    for fid in config.INVENTORY_FIELDS:
        checks = [{k:v for k,v in spec.items() if k!='check'} for spec in RULES if fid in spec['fields']]
        fields.append({**config.field_definition(fid),'source':mapping.get(fid) if mapping else None,
                       'checks':checks,'rules':' '.join(c['requirement'] for c in checks)})
    return fields


def validate_row(inputs, source_row, as_of, formulas=(), groups=None, missing_columns=()):
    product, problems = normalize(inputs,formulas)
    c = Context(inputs,product,dict(problems),set(formulas),source_row,as_of,groups or {},set(missing_columns))
    findings = []
    for spec in RULES:
        c.current = spec
        missing = [f for f in spec['depends'] if f in c.problems or not product.get(f)]
        if missing:
            c.skip(missing)
            continue
        for fields,message in spec['check'](c):
            findings.append(Finding(spec['id'],spec['severity'],text(inputs.get('response_id')),
                source_row,text(inputs.get('system_name')),fields,
                {config.LABELS[f]:inputs.get(f,'') for f in fields},message,spec['action'],
                spec['title'],spec['requirement'],spec['why']))
    return product,findings,c.not_checked


def validate_upload(parsed, as_of):
    if parsed.mapping is None:
        raise ValueError('Confirm the column mapping before validating.')
    mapped = []
    groups = {f:defaultdict(list) for f in ['response_id','application_id','system_name']}
    for row in parsed.rows:
        values = {f:row['values'].get(column,'') if column else '' for f,column in parsed.mapping.items()}
        formulas = {f for f,column in parsed.mapping.items() if column in row['formulas']}
        mapped.append((row,values,formulas))
        for f,group in groups.items():
            value = ' '.join(text(values[f]).casefold().split())
            if value and value not in config.PLACEHOLDERS and f not in formulas:
                group[value].append(row['source_row'])
    missing = {f for f,column in parsed.mapping.items() if column is None}
    records = []
    for index,(row,values,formulas) in enumerate(mapped):
        _,findings,not_checked = validate_row(values,row['source_row'],as_of,formulas=formulas,groups=groups,missing_columns=missing)
        issues = [f.to_dict() for f in findings]
        errors = sum(f.severity=='ERROR' for f in findings)
        warnings = len(findings)-errors
        unchecked_fields = {f for c in not_checked for f in c['fields']}
        field_results = {}
        for fid in config.INVENTORY_FIELDS:
            relevant = [f for f in findings if fid in f.fields]
            field_results[fid] = ('Error' if any(f.severity=='ERROR' for f in relevant) else
                                  'Warning' if relevant else 'Not checked' if fid in unchecked_fields else
                                  'Not provided' if not text(values[fid]) else 'No issues')
        records.append({'key':index,'source_row':row['source_row'],'response_id':text(values['response_id']),
            'name':text(values['system_name']),'owner':text(values['business_owner_email']),
            'cells':values,'source_values':row['values'],'findings':issues,'not_checked':not_checked,
            'field_results':field_results,'errors':errors,'warnings':warnings,
            'status':'Failed' if errors else 'Needs review' if warnings or not_checked else 'Passed',
            'affected_fields':list(dict.fromkeys(f for issue in issues for f in issue['fields']))})
    return {'profile':'inventory','fields':catalogue(parsed.mapping),'records':records,
            'mapping':parsed.mapping,'source_columns':parsed.columns,'as_of':as_of.isoformat(),
            'rules_version':config.RULES_VERSION,
            'missing_required':[f for f in config.INVENTORY_FIELDS if f in config.REQUIRED and f in missing]}
