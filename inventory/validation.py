"""Executable error rules shared by record validation, field help and reports."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date
from functools import lru_cache
from html import unescape
import re
from email_validator import validate_email, EmailNotValidError
import inventory as config
from inventory.normalization import category, normalize, text
from inventory.analytics import invalid_chart_fields

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
    source_row: int
    as_of: date
    groups: dict = dc_field(default_factory=dict)
    source_values: dict = dc_field(default_factory=dict)
    not_checked: list = dc_field(default_factory=list)
    current: dict = dc_field(default_factory=dict)

    def invalid(self, *fields):
        blocked = [f for f in fields if f in self.problems]
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


# Extract full candidates so an invalid address cannot pass through a valid substring.
EMAIL_PATTERN = re.compile(r"(?<![\w.!#$%&'*+/=?^`{|}~@-])[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]+(?![\w@-])")


@lru_cache(maxsize=20000)
def emails_in_text(value):
    return tuple(dict.fromkeys(candidate for candidate in EMAIL_PATTERN.findall(unescape(value)) if valid_email(candidate)))


def placeholder_text(value):
    value = re.sub(r'\s+',' ',text(value)).casefold()
    return value in config.PLACEHOLDERS or not any(ch.isalpha() for ch in value)


def value_hint(field):
    if field in OWNERS:
        return 'Enter the owner’s name or a valid email address from any domain. Names, roles, notes and multiple contacts are accepted.'
    if field == 'business_purpose':
        return 'Describe what the system does and who uses it. Example: Helps claims staff find approved internal guidance.'
    if field == 'system_name':
        return 'Enter the actual name of the AI system or solution.'
    if field == 'submitter_name':
        return 'Enter the name of the person submitting this inventory record.'
    if field == 'application_id':
        return 'Enter the Application ID/System ID or Not Available.'
    definition = config.field_definition(field)
    return 'Enter '+config.LABELS[field]+'. '+definition['format']


@rule('REQ-01','Complete the required field',sorted(config.REQUIRED),
      'Every required inventory field must contain a value.',
      'Enter the missing value in the source file, then upload the file again.')
def required(c):
    for f in sorted(config.REQUIRED):
        if not text(c.inputs.get(f)) or (f in config.MULTI and f not in c.problems and not c.product[f]):
            yield [f], config.LABELS[f]+' is blank.', value_hint(f)


def format_rule(identifier, title, fields, requirement, fix):
    @rule(identifier,title,fields,requirement,fix)
    def check(c):
        for f in fields:
            if f in c.problems:
                yield [f], config.LABELS[f]+': '+c.problems[f]


format_rule('COUNT-01','Enter a whole-number model count',sorted(config.COUNTS),
            'Use a whole number of 0 or greater; a leading count with explanatory notes is accepted. Blank, Unknown and Not Applicable are accepted when a numeric count is not required by the selected technologies.',
            'Count the actual models used and enter that whole number. ML, DL and Predictive Analytics require at least 1; LLM, GenAI and Agentic AI allow 0.')
format_rule('DATE-01','Correct the date',sorted(config.DATES),
            'Use YYYY-MM-DD, M/D/YYYY, or M/D/YY. Slash dates use month/day order.',
            'Enter a real calendar date, preferably using YYYY-MM-DD. Do not use a numeric Excel date serial or a description such as tomorrow.')
format_rule('ENUM-01','Provide a selection',[*config.OPTIONS, 'impact'],
            'Required selections cannot consist only of separators. Deployment Status must contain one status. Source wording and choices outside the examples are accepted.',
            'Enter the actual selection. For Deployment Status, select one current status.')


OWNERS = ['business_owner_email','technical_owner_email']
PEOPLE = OWNERS


@rule('REQ-02','Identify the person',PEOPLE,
      'Owners may be identified by name or a valid email from any domain. Missing-contact placeholders and values with no letters do not identify an owner.',
      'Enter the owner’s name or a valid email address from any domain.')
def people(c):
    for f in PEOPLE:
        value = text(c.inputs.get(f))
        if value and (placeholder_text(value) or not any(ch.isalpha() for ch in value)):
            yield [f], config.LABELS[f]+' does not identify a person.', value_hint(f)


@rule('EMAIL-01','Correct the owner email',OWNERS,
      'Owner names are accepted. When email text is supplied, include at least one syntactically valid email address from any domain. Multiple addresses and surrounding text are accepted. Delivery, directory membership and identity matching are not checked.',
      'Correct the owner email to a valid address from any domain, or identify the owner by name.')
def owner_email(c):
    for f in OWNERS:
        value = text(c.inputs.get(f))
        if '@' in unescape(value) and not emails_in_text(value):
            yield [f], config.LABELS[f]+' contains email text but no valid email address.'


@rule('EMAIL-02','Correct the vendor email',['vendor_owner'],
      'Vendor contacts may use names or emails from any domain. If email text is supplied, it must contain at least one syntactically valid address; surrounding notes and multiple addresses are accepted.',
      'Correct the vendor email address, or supply the vendor and accountable contact by name.')
def vendor_email(c):
    value = unescape(text(c.inputs.get('vendor_owner')))
    if '@' in value and not emails_in_text(value):
        yield ['vendor_owner'], 'Vendor Owner contains email text but no valid email address.'


@rule('VENDOR-01','Identify the vendor contact',['ai_source','vendor_owner'],
      'Vendor Owner is required when Source of AI System identifies a vendor-built, licensed, purchased or hybrid solution. A platform name, Other or Unknown alone does not establish vendor involvement.',
      'Enter the vendor contact’s name or email in Vendor Owner.',depends=['ai_source'])
def vendor(c):
    source = c.product['ai_source']
    if source == 'Other':
        source, _ = category(c.product['other_details'].get('ai_source',''), 'ai_source')
    contact = unescape(text(c.inputs.get('vendor_owner')))
    if source in config.VENDOR_SOURCES and (placeholder_text(contact) or contact.casefold() == 'not applicable'):
        yield ['vendor_owner'], 'The selected source indicates vendor involvement, but Vendor Owner is blank or marked unavailable.'


def model_rule(identifier, field, technologies, title, minimum=1):
    @rule(identifier,title,['ai_types',field],
          'When '+', '.join(sorted(technologies))+' is selected, '+config.LABELS[field]+' must be a whole number of at least '+str(minimum)+'.',
          'Enter the actual whole-number model count. ML, DL and Predictive Analytics require at least 1; LLM, GenAI and Agentic AI allow 0.',depends=['ai_types'])
    def check(c):
        selected = set(c.product['ai_types'])
        if selected & technologies and not c.invalid(field) and (c.product[field] is None or c.product[field] < minimum):
            yield ['ai_types',field], ('The selected AI technology requires a numeric '+config.LABELS[field]+' of at least '+str(minimum)+', but the submitted value is '+(text(c.inputs.get(field)) or 'blank')+'.')


model_rule('COUNT-02','llm_count',{'Large Language Model (LLM)','Generative AI (GenAI)','Agentic AI'},'Provide the number of LLMs used',minimum=0)
model_rule('COUNT-03','ml_dl_count',{'Machine Learning (ML)','Deep Learning (DL)','Predictive Analytics'},'Provide the number of ML/DL models used')


@rule('DATE-05','Correct the submission date',['submitted_date'],
      'Date Submitted must be on or before the saved validation date.',
      'Enter the date this inventory information was actually submitted, using YYYY-MM-DD.')
def submitted_date(c):
    value = c.product['submitted_date']
    if not c.invalid('submitted_date') and value and date.fromisoformat(value)>c.as_of:
        yield ['submitted_date'], 'Date Submitted is in the future relative to the validation date, '+c.as_of.isoformat()+'.'


@rule('DATE-02','Provide the go-live date',['deployment_status','go_live_date'],
      'An Active system must have a valid go-live date. Future go-live dates are accepted for every deployment status.',
      'Enter the go-live date using YYYY-MM-DD. Planned future dates are accepted.',depends=['deployment_status'])
def active_date(c):
    if c.product['deployment_status']=='Active' and not c.invalid('go_live_date'):
        value = c.product['go_live_date']
        if not value:
            yield ['deployment_status','go_live_date'], 'The system is Active, but its go-live date is missing.'


@rule('SCOPE-01','Correct the scope selections',['lines_of_business','states'],
      'None must stand alone. All States must stand alone.',
      'Keep the exclusive choice alone, or remove it and select the actual lines of business or states. Separate multiple selections with semicolons.')
def exclusive_scope(c):
    for f,exclusive in [('lines_of_business',{'None'}),('states',{'None','All States'})]:
        if f not in c.problems and len(c.product[f])>1 and set(c.product[f]) & exclusive:
            yield [f], config.LABELS[f]+' combines a choice that must stand alone with another selection.'


@rule('ID-02','Use a unique application ID',['application_id'],
      'An actual Application / System ID must be unique within the file. Repeated unavailable-ID placeholders are allowed.',
      'Check the listed source rows. Remove unintended duplicate records, or enter the correct unique ID for each distinct system.')
def duplicate_id(c):
    value = ' '.join(text(c.inputs.get('application_id')).casefold().split())
    rows = c.groups.get(value,[])
    if len(rows)>1:
        detail = ', '.join(map(str,rows[:20])) + (f' and {len(rows)-20} more' if len(rows)>20 else '')
        yield ['application_id'], 'This application ID is repeated in source rows '+detail+'.'


def catalogue():
    return [{**config.field_definition(fid),
             'checks':[{k:v for k,v in spec.items() if k not in {'check','depends'}} for spec in RULES if fid in spec['fields']]}
            for fid in config.INVENTORY_FIELDS]


def validate_row(inputs, source_row, as_of, groups=None, source_values=None):
    product, problems = normalize(inputs)
    c = Context(inputs,product,dict(problems),source_row,as_of,groups=groups or {},source_values=source_values or {})
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
    extra_columns = [column for column in parsed.columns if column not in parsed.field_columns.values()]
    groups = defaultdict(list)
    for row in parsed.rows:
        values = {f:row['values'][parsed.field_columns[f]] for f in config.INVENTORY_FIELDS}
        prepared.append((row,values))
        value = ' '.join(text(values['application_id']).casefold().split())
        if value and value not in config.PLACEHOLDERS:
            groups[value].append(row['source_row'])
    for index,(row,values) in enumerate(prepared):
        product,findings,not_checked = validate_row(values,row['source_row'],as_of,groups,row['values'])
        issues = [f.to_dict() for f in findings]
        affected = list(dict.fromkeys(f for issue in issues for f in issue['fields']))
        dependent = {f for c in not_checked for f in c['fields']}
        field_results = {f: ('Error' if f in affected else 'Depends on another field' if f in dependent else
                             'Blank — optional' if not text(values[f]) else 'No errors') for f in config.INVENTORY_FIELDS}
        records.append({'key':index,'source_row':row['source_row'],'application_id':text(values['application_id']),
            'name':text(values['system_name']),'owner':text(values['business_owner_email']),
            'cells':values,'source_values':row['values'],'findings':issues,'not_checked':not_checked,
            'extra_values':{column:row['values'][column] for column in extra_columns},
            'normalized':product,'chart_invalid_fields':invalid_chart_fields(issues),
            'field_results':field_results,'errors':len(findings),'status':'Errors' if findings else 'Passed','affected_fields':affected})
    return {'fields':catalogue(),'records':records,'source_columns':parsed.columns,'input_layout':parsed.layout,
            'as_of':as_of.isoformat(),'schema_version':config.SCHEMA_VERSION,'rules_version':config.RULES_VERSION}
