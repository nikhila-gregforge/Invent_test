"""Regressions for the supplied layers and confirmed owner/model-count policies."""
import pytest
from inventory import FIELDS, OPTIONS, VENDOR_SOURCES
from inventory.validation import emails_in_text
from test_inventory import valid_row, validate, rules, snapshot


@pytest.mark.parametrize('question', ['Q1','Q2','Q3','Q4','Q5','Q6','Q7','Q9','Q10',
                                    'Q13','Q14','Q15','Q16','Q18','Q19','Q20','Q21','Q22','Q23'])
def test_each_unconditionally_required_field_rejects_whitespace(question):
    _, findings, _ = validate(**{question:' \t\n '})
    assert any(f.rule_id=='REQ-01' and FIELDS[question] in f.fields for f in findings)


@pytest.mark.parametrize('question',['Q4','Q9','Q10','Q13','Q14','Q15','Q16','Q18','Q19','Q20','Q21'])
def test_separator_only_choices_are_record_errors(question):
    result=snapshot([valid_row(),valid_row('002',**{question:' ; ;\t;'})])['records']
    assert result[0]['status']=='Passed'
    assert result[1]['status']=='Errors'
    assert any(f['rule_id']=='ENUM-01' and FIELDS[question] in f['fields'] for f in result[1]['findings'])


@pytest.mark.parametrize('value',['???','!!!','---','🚩','123.45'])
def test_contact_still_identifies_someone_without_policing_descriptive_wording(value):
    assert not validate(Q2=value,Q3=value)[1]
    assert 'VENDOR-01' in rules(validate(Q9='Hybrid (in-house + vendor components)',Q8=value)[1])


@pytest.mark.parametrize('value',['N/A','TBD','None','NA','null','not provided','???','Unknown...'])
def test_nonblank_application_id_wording_is_not_rejected(value):
    assert not validate(Q1=value)[1]


@pytest.mark.parametrize('value',['Not Available','Unknown',' not   available ','00123','123-456','APP-123'])
def test_valid_application_ids_and_documented_exceptions(value):
    assert not validate(Q1=value)[1]


@pytest.mark.parametrize('value',[
    'Alex Smith <alex.smith@centene.com> — Claims operations',
    'Email: alex.smith@centene.com (primary); taylor@centene.com (backup)',
    'Contact ALEX@CENTENE.COM, ext. 1234.',
    'Primary: alex+claims@centene.com\nSecondary: taylor@centene.com',
    'mailto:alex@centene.com',
    'Contact alex@centene.com. Available Monday–Friday.',
])
def test_extract_centene_emails_from_descriptive_text(value):
    assert emails_in_text(value)
    assert not validate(Q6=value,Q7=value)[1]


@pytest.mark.parametrize('value',[
    'Contact: alex@', 'Contact: alex@centene',
    'alex@centene.com.evil.example', 'alex@notcentene.com',
    'wrong@alex@centene.com', 'alex@centene.com@evil.example',
    'alex..smith@centene.com', 'alex@centene..com',
    'alex@subdomain.centene.com', 'External contact <alex@example.com>',
])
def test_email_extraction_does_not_accept_invalid_or_external_substrings(value):
    assert 'EMAIL-01' in rules(validate(Q6=value,Q7=value)[1])


def test_email_text_policy_preserves_original_input_and_accepts_vendor_domains():
    original='Alex <alex@centene.com> and vendor contact <vendor@example.com>'
    record=snapshot([valid_row(Q6=original,Q8='Vendor <vendor@example.com> (support)')])['records'][0]
    assert record['status']=='Passed' and record['cells']['business_owner_email']==original
    assert 'EMAIL-02' in rules(validate(Q8='Vendor email: broken@')[1])


@pytest.mark.parametrize('source',sorted(VENDOR_SOURCES))
@pytest.mark.parametrize('contact',['', 'N/A', 'None', 'Not Applicable', 'N&#47;A'])
def test_explicit_vendor_sources_require_contact_and_only_flag_vendor_owner(source,contact):
    findings=validate(Q9=source,Q8=contact)[1]
    assert len(findings)==1 and findings[0].rule_id=='VENDOR-01'
    assert findings[0].fields==['vendor_owner']
    assert not validate(Q9=source,Q8='Example Vendor — Alex Smith')[1]


@pytest.mark.parametrize('source',[
    'Developed in-house', 'DEVELOPED IN-HOUSE', 'Developed in house',
    'Copilot Studio', 'AI builders in MS Power Automate, accessed from Power Platform',
    'Development is planned in-house, with possible vendor MCP server. Unknown until prototype is built.',
    'Other', 'Other: Research prototype', 'Unknown',
])
def test_platforms_and_uncertain_sources_do_not_invent_vendor_involvement(source):
    record=snapshot([valid_row(Q9=source,Q8='N/A')])['records'][0]
    assert record['status']=='Passed'
    assert record['cells']['ai_source']==source
    assert record['cells']['vendor_owner']=='N/A'


@pytest.mark.parametrize('source',[
    'Vendor-built', 'Vendor built, in-application features',
    'Licensed from vendor', 'Off-the-shelf', 'Hybrid',
    'Other: Vendor built', 'Other: Licensed from vendor',
])
def test_explicit_vendor_wording_and_notes_still_require_a_contact(source):
    assert 'VENDOR-01' in rules(validate(Q9=source,Q8='N/A')[1])


def test_missing_source_flags_source_without_inventing_vendor_involvement():
    record=snapshot([valid_row(Q9='',Q8='')])['records'][0]
    assert record['errors']==1 and record['affected_fields']==['ai_source']
    assert record['findings'][0]['rule_id']=='REQ-01'


@pytest.mark.parametrize('technology',['ML','DL','Predictive Analytics'])
@pytest.mark.parametrize('count',['','0','Unknown','TBD'])
def test_ml_dl_predictive_require_a_positive_numeric_count(technology,count):
    assert 'COUNT-03' in rules(validate(Q10=technology,Q11=count)[1])


@pytest.mark.parametrize('technology',['GenAI','Agentic AI'])
@pytest.mark.parametrize('count',['','Unknown','TBD','Not Available'])
def test_genai_agentic_require_numeric_llm_count(technology,count):
    assert 'COUNT-02' in rules(validate(Q10=technology,Q12=count)[1])


def test_zero_llms_allowed_with_all_llm_related_technologies():
    assert not validate(Q10='GenAI;Agentic AI',Q12='0')[1]
    findings=validate(Q10='GenAI;Agentic AI;LLM',Q12='0')[1]
    assert not findings


@pytest.mark.parametrize('status',OPTIONS['deployment_status'])
def test_future_go_live_dates_are_accepted_in_every_lifecycle(status):
    product,findings,_=validate(Q16=status,Q17='2030-01-01')
    assert not findings and product['go_live_date']=='2030-01-01'


def test_state_alias_from_validation_layers_and_exclusivity():
    assert not validate(Q19='None (Internal / Enterprise-Wide Functions)')[1]
    assert 'SCOPE-01' in rules(validate(Q19='None (Internal / Enterprise-Wide Functions);All States')[1])


def test_owner_names_are_accepted_without_an_email_anywhere_in_the_row():
    record=snapshot([valid_row(Q6='Alex Smith',Q7='Taylor Jones')])['records'][0]
    assert record['status']=='Passed'
    assert record['field_results']['technical_owner_email']=='No errors'
    assert record['cells']['technical_owner_email']=='Taylor Jones'


def test_owner_names_and_vendor_email_are_independently_accepted():
    record=snapshot([valid_row(Q6='Alex Smith',Q7='Taylor Jones',Q8='Support: vendor@centene.com')])['records'][0]
    assert record['affected_fields']==[]
    assert record['field_results']['technical_owner_email']=='No errors'


@pytest.mark.parametrize('technical',['','???','Unknown','wrong@','wrong@external.example'])
def test_other_row_email_does_not_rescue_missing_placeholder_or_invalid_technical_owner(technical):
    record=snapshot([valid_row(Q7=technical)])['records'][0]
    assert 'technical_owner_email' in record['affected_fields']


def test_email_in_another_record_does_not_rescue_an_invalid_email():
    records=snapshot([valid_row(),valid_row('002',Q6='alex@',Q7='taylor@')])['records']
    assert records[0]['status']=='Passed'
    assert set(records[1]['affected_fields'])=={'business_owner_email','technical_owner_email'}


@pytest.mark.parametrize('value,expected',[
    ('1, Google Gemini',1), ('1 (embedding model).',1),
    ('ML/DL Models Count: 4 (Transcription and text-to-speech)',4),
    ('4 - Gemini 2.5',4), ('10 LLMs',10), ('2 models',2),
    ('1- We use a language model',1), ('0 (confirmation pending)',0),
    ('2&#160;(production models)',2),
])
def test_explicit_count_with_notes_is_not_a_format_error(value,expected):
    product,findings,_=validate(Q10='RPA',Q11=value,Q12=value)
    assert not findings
    assert product['ml_dl_count']==product['llm_count']==expected


@pytest.mark.parametrize('value',[
    'GPT 5.4','Claude 4.6','4-12','4 - 12','8+','1. Claude',
    '1. Claude\n2. Gemini','7 MLs 1 DL','1,365 Copilot','1.5 (production models)',
])
def test_ambiguous_or_fractional_count_is_not_guessed(value):
    assert 'COUNT-01' in rules(validate(Q12=value)[1])


def test_annotated_zero_still_obeys_technology_minimum():
    assert not validate(Q10='LLM',Q12='0 (not deployed yet)')[1]
    assert 'COUNT-03' in rules(validate(Q10='ML',Q11='0 (not deployed yet)')[1])


def test_html_encoded_email_and_raw_cell_preservation():
    value='Alex &lt;alex&#64;centene.com&gt; — primary'
    record=snapshot([valid_row(Q6=value)])['records'][0]
    assert record['status']=='Passed' and record['cells']['business_owner_email']==value


@pytest.mark.parametrize('question,value', [
    ('Q4','Communications'), ('Q5','Regulatory; Financial; Patient'),
    ('Q13','Business Confidential Data'), ('Q14','Jira'),
    ('Q15','Copilot Studio'), ('Q18','Corporate'),
    ('Q20','Very Low'), ('Q21','Human review before release'),
])
def test_choices_and_profiles_outside_chart_catalogue_are_preserved_without_errors(question,value):
    record=snapshot([valid_row(**{question:value})])['records'][0]
    assert record['status']=='Passed'
    assert record['cells'][FIELDS[question]]==value


def test_unknown_choices_do_not_hide_known_technology_requirements_or_scope_conflicts():
    assert 'COUNT-03' in rules(validate(Q10='Custom classifier, ML, NLP',Q11='0')[1])
    assert 'COUNT-02' in rules(validate(Q10='LLM, Custom technology',Q12='')[1])
    assert 'SCOPE-01' in rules(validate(Q18='None, Corporate')[1])


def test_optional_counts_accept_not_applicable_but_required_counts_remain_numeric():
    assert not validate(Q10='RPA',Q11='N/A',Q12='Not Applicable')[1]
    assert 'COUNT-02' in rules(validate(Q10='LLM',Q12='N/A')[1])
    assert 'COUNT-03' in rules(validate(Q10='ML',Q11='N/A')[1])
    assert not validate(Q9='Other',Q8='Example support team')[1]
