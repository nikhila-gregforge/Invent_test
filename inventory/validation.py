"""Executable error rules shared by record validation, field help and reports."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date
from functools import lru_cache
import re
from email_validator import validate_email, EmailNotValidError
import inventory as config
from inventory.normalization import normalize, text

RULES = []


def rule(identifier, title, fields, requirement, fix, depends=()):
    def register(check):
        RULES.append(dict(id=identifier,title=title,fields=list(fields),requirement=requirement,
                          fix=fix,depends=list(depends),check=check))
        return check
    return register


@dataclass
class Finding:
    rule_id: str
    fields: list
    message: str
    fix: str
    title: str
    requirement: str

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
    not_checked: list = dc_field(default_factory=list)
    current: dict = dc_field(default_factory=dict)

    def invalid(self, *fields):
        blocked = [f for f in fields if f in self.problems or f in self.formulas]
        if blocked:
            self.skip(blocked)
        return bool(blocked)

    def skip(self, fields):
        item = {'rule_id':self.current['id'],'title':self.current['title'],
                'fields':self.current['fields'],'blocked_by':fields,
                'reason':'Fix '+', '.join(config.LABELS[f] for f in fields)+' in the source file first, then upload again to complete this check.'}
        if item not in self.not_checked:
            self.not_checked.append(item)


@lru_cache(maxsize=20000)
def valid_email(value):
    try:
        validate_email(value,check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def placeholder_text(value):
    value = re.sub(r'\s+',' ',text(value)).casefold().strip(' .!_-')
    return value in config.PLACEHOLDERS or value.isnumeric() or bool(re.fullmatch(
        r'(?:(?:this is|just|for) (?:a )?)?(?:test(?:ing)?(?:[\s._-]*(?:test|\d+|agent|description|purpose|system|name|data))*)'
        r'|new agent(?:[\s._-]*\d+)?|untitled(?: agent)?|dummy|sample|asdf|abc',value))


def value_hint(field):
    if field in OWNERS:
        return 'Enter the accountable person’s name, optionally with role or department, or one valid email address.'
    if field == 'business_purpose':
        return 'Describe what the system does and who uses it. Example: Helps claims staff find approved internal guidance.'
    if field == 'system_name':
        return 'Enter the actual name of the AI system or solution.'
    if field == 'submitter_name':
        return 'Enter the name of the person submitting this inventory record.'
    if field == 'application_id':
        return 'Enter the application’s unique ID. If it is unavailable, enter Not Available.'
    definition = config.field_definition(field)
    return 'Enter '+config.LABELS[field]+'. '+definition['format']


@rule('REQ-01','Complete the required field',sorted(config.REQUIRED),
      'Every required inventory field must contain a value.',
      'Enter the missing value in the source file, then upload the file again.')
def required(c):
    for f in sorted(config.REQUIRED):
        if not text(c.inputs.get(f)) or (f in config.MULTI and f not in c.problems and not c.product[f]):
            yield [f], config.LABELS[f]+' is blank.', value_hint(f)


@rule('FORMULA-01','Provide the actual value',config.INVENTORY_FIELDS,
      'Inventory cells must contain literal values. Excel formulas are not evaluated.',
      'In the source workbook, replace the formula with its calculated value using Paste Special → Values, then upload again.')
def formulas(c):
    for f in sorted(c.formulas):
        yield [f], 'This cell contains an Excel formula, so its actual value cannot be validated.'


def format_rule(identifier, title, fields, requirement, fix):
    @rule(identifier,title,fields,requirement,fix)
    def check(c):
        for f in fields:
            if f in c.problems and f not in c.formulas:
                yield [f], config.LABELS[f]+': '+c.problems[f]


format_rule('COUNT-01','Enter a whole-number model count',sorted(config.COUNTS),
            'Use 0 or a whole number above 0. Blank, Unknown, TBD and Not Available are accepted unless the selected model type requires a positive count.',
            'Count the actual models used and enter that whole number, such as 0, 1 or 2. A declared LLM or ML/DL model type requires at least 1 in its corresponding count.')
format_rule('DATE-01','Correct the date',sorted(config.DATES),
            'Use YYYY-MM-DD, M/D/YYYY, M/D/YY, or an Excel date cell. Slash dates use month/day order.',
            'Enter a real calendar date, preferably using YYYY-MM-DD. Do not use a numeric Excel date serial or a description such as tomorrow.')
format_rule('ENUM-01','Use an accepted value',list(config.OPTIONS),
            'Use the accepted values for this field. Separate multiple selections with semicolons. Other requires a description.',
            'Replace the value with an accepted choice listed under View field rules. For Other, enter Other: followed by a description.')
format_rule('IMPACT-01','Complete the impact profile',['impact'],
            'Supply Member, Regulatory and Financial exactly once each, using Yes, No or Unknown.',
            'Enter all three actual impact values, for example Member: No; Regulatory: No; Financial: Yes. Change the example values to match this system.')


@rule('TEXT-01','Describe the actual system',['system_name','business_purpose'],
      'The system name and purpose must describe the real system. Test-only text, generic placeholders and numbers alone are not accepted.',
      'Replace the placeholder with the actual system name or a description of its purpose.')
def purpose(c):
    for f in ['system_name','business_purpose']:
        if f not in c.formulas and text(c.inputs.get(f)) and placeholder_text(c.inputs[f]):
            yield [f], ('This description does not explain what the system does.' if f=='business_purpose'
                        else 'This placeholder does not identify the AI system.'), value_hint(f)


OWNERS = ['business_owner_email','technical_owner_email']
PEOPLE = [*OWNERS,'submitter_name']


@rule('REQ-02','Identify the person',PEOPLE,
      'Owners accept a person’s name or one valid email. The submitter must have a meaningful name. Placeholder values and values with no letters are not accepted.',
      'Enter the person’s name, with role or department if useful. An owner may also be identified by one valid email.')
def people(c):
    for f in PEOPLE:
        value = text(c.inputs.get(f))
        if f not in c.formulas and value and (placeholder_text(value) or not any(ch.isalpha() for ch in value)):
            yield [f], config.LABELS[f]+' does not identify a person.', value_hint(f)


@rule('EMAIL-01','Correct the owner email',OWNERS,
      'A person’s name or one syntactically valid email is accepted. A value containing @ must be a valid email; any domain is allowed.',
      'Correct the email address and include only one address, or replace it with the accountable person’s name.')
def owner_email(c):
    for f in OWNERS:
        value = text(c.inputs.get(f))
        if f not in c.formulas and '@' in value and not valid_email(value):
            yield [f], 'The email entered for '+config.LABELS[f]+' is not a valid single email address.'


@rule('VENDOR-01','Identify the vendor contact',['ai_source','vendor_owner'],
      'Vendor-built, licensed, off-the-shelf and hybrid systems require an accountable vendor contact. Other acquisition sources do not require one.',
      'Enter the vendor name and accountable contact in Vendor Owner. Example: Example Vendor — Alex Smith.',depends=['ai_source'])
def vendor(c):
    if c.product['ai_source'] in config.OPTIONS['ai_source'][1:5] and not c.invalid('vendor_owner') and placeholder_text(c.inputs.get('vendor_owner')):
        yield ['ai_source','vendor_owner'], 'The selected acquisition source involves a vendor, but Vendor Owner does not identify a contact.'


def model_rule(identifier, field, technologies, title):
    @rule(identifier,title,['ai_types',field],
          'When '+', '.join(sorted(technologies))+' is selected, '+config.LABELS[field]+' must be a whole number greater than 0.',
          'Enter the actual positive model count. If this system does not use the selected model type, correct Type(s) of AI Used instead.',depends=['ai_types'])
    def check(c):
        if set(c.product['ai_types']) & technologies and not c.invalid(field) and not (c.product[field] or 0)>0:
            yield ['ai_types',field], ('The selected AI technology requires at least one model, but '+config.LABELS[field]+' is '+(text(c.inputs.get(field)) or 'blank')+'.')


model_rule('COUNT-02','llm_count',{'Large Language Model (LLM)'},'Provide the number of LLMs used')
model_rule('COUNT-03','ml_dl_count',{'Machine Learning (ML)','Deep Learning (DL)'},'Provide the number of ML/DL models used')


@rule('DATE-05','Correct the submission date',['submitted_date'],
      'Date Submitted must be on or before the saved validation date.',
      'Enter the date this inventory information was actually submitted, using YYYY-MM-DD.')
def submitted_date(c):
    value = c.product['submitted_date']
    if not c.invalid('submitted_date') and value and date.fromisoformat(value)>c.as_of:
        yield ['submitted_date'], 'Date Submitted is in the future relative to the validation date, '+c.as_of.isoformat()+'.'


@rule('DATE-02','Provide the actual go-live date',['deployment_status','go_live_date'],
      'An Active system must have an actual go-live date on or before the validation date. A valid planned date is allowed for other deployment statuses.',
      'Enter the actual go-live date using YYYY-MM-DD. If the system is not yet operational, correct Deployment Status.',depends=['deployment_status'])
def active_date(c):
    if c.product['deployment_status']=='Active' and not c.invalid('go_live_date'):
        value = c.product['go_live_date']
        if not value:
            yield ['deployment_status','go_live_date'], 'The system is Active, but its go-live date is missing.'
        elif date.fromisoformat(value)>c.as_of:
            yield ['deployment_status','go_live_date'], 'The system is Active, but its go-live date is later than the validation date, '+c.as_of.isoformat()+'.'


@rule('SCOPE-01','Correct the scope selections',['lines_of_business','states'],
      'None must stand alone. All States must stand alone.',
      'Keep the exclusive choice alone, or remove it and select the actual lines of business or states. Separate multiple selections with semicolons.')
def exclusive_scope(c):
    for f,exclusive in [('lines_of_business',{'None'}),('states',{'None','All States'})]:
        if f not in c.problems and len(c.product[f])>1 and set(c.product[f]) & exclusive:
            yield [f], config.LABELS[f]+' combines a choice that must stand alone with another selection.'


@rule('SCOPE-02','Identify the Medicaid jurisdiction',['lines_of_business','states'],
      'Medicaid use requires at least one state, District of Columbia or All States.',
      'Enter the state or states where this system supports Medicaid. Use All States only if it applies to every state.',depends=['lines_of_business'])
def medicaid(c):
    if 'Medicaid' in c.product['lines_of_business']:
        if c.invalid('states'):
            return
        if 'None' in c.product['states']:
            yield ['lines_of_business','states'], 'Medicaid is selected, but State is set to None.'
        elif not c.product['states']:
            c.skip(['states'])


@rule('ID-02','Use a unique application ID',['application_id'],
      'An actual Application / System ID must be unique within the file. Repeated Not Available or Unknown values are allowed.',
      'Check the listed source rows. Remove unintended duplicate records, or enter the correct unique ID for each distinct system.')
def duplicate_id(c):
    value = ' '.join(text(c.inputs.get('application_id')).casefold().split())
    rows = c.groups.get(value,[])
    if len(rows)>1 and 'application_id' not in c.formulas:
        detail = ', '.join(map(str,rows[:20])) + (f' and {len(rows)-20} more' if len(rows)>20 else '')
        yield ['application_id'], 'This application ID is repeated in source rows '+detail+'.'


def catalogue():
    return [{**config.field_definition(fid),
             'checks':[{k:v for k,v in spec.items() if k not in {'check','depends'}} for spec in RULES if fid in spec['fields']]}
            for fid in config.INVENTORY_FIELDS]


def validate_row(inputs, source_row, as_of, formulas=(), groups=None):
    product, problems = normalize(inputs,formulas)
    c = Context(inputs,product,dict(problems),set(formulas),source_row,as_of,groups or {})
    findings = []
    for spec in RULES:
        c.current = spec
        missing = [f for f in spec['depends'] if f in c.problems or not product.get(f)]
        if missing:
            c.skip(missing)
            continue
        for result in spec['check'](c):
            fields,message,*fix = result
            findings.append(Finding(spec['id'],fields,message,fix[0] if fix else spec['fix'],spec['title'],spec['requirement']))
    # Every blocked check has an underlying error. Never call incomplete validation a pass.
    if c.not_checked and not findings:
        raise RuntimeError('A blocked validation check has no underlying error.')
    return product,findings,c.not_checked


def validate_upload(parsed, as_of):
    records, prepared = [], []
    groups = defaultdict(list)
    for row in parsed.rows:
        values = {f:row['values'][config.LABELS[f]] for f in config.INVENTORY_FIELDS}
        formulas = {f for f in config.INVENTORY_FIELDS if config.LABELS[f] in row['formulas']}
        prepared.append((row,values,formulas))
        value = ' '.join(text(values['application_id']).casefold().split())
        if value and value not in {'not available','unknown'} and 'application_id' not in formulas:
            groups[value].append(row['source_row'])
    for index,(row,values,formulas) in enumerate(prepared):
        _,findings,not_checked = validate_row(values,row['source_row'],as_of,formulas,groups)
        issues = [f.to_dict() for f in findings]
        affected = list(dict.fromkeys(f for issue in issues for f in issue['fields']))
        dependent = {f for c in not_checked for f in c['fields']}
        field_results = {f: ('Error' if f in affected else 'Depends on another field' if f in dependent else
                             'Blank — optional' if not text(values[f]) else 'No errors') for f in config.INVENTORY_FIELDS}
        records.append({'key':index,'source_row':row['source_row'],'application_id':text(values['application_id']),
            'name':text(values['system_name']),'owner':text(values['business_owner_email']),
            'cells':values,'source_values':row['values'],'findings':issues,'not_checked':not_checked,
            'field_results':field_results,'errors':len(findings),'status':'Errors' if findings else 'Passed','affected_fields':affected})
    return {'fields':catalogue(),'records':records,'source_columns':parsed.columns,
            'as_of':as_of.isoformat(),'schema_version':config.SCHEMA_VERSION,'rules_version':config.RULES_VERSION}
