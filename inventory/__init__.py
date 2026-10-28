"""Fixed inventory columns, accepted cell values and field guidance."""
import os
from pathlib import Path

RULES_VERSION = '5.4'
SCHEMA_VERSION = 'inventory-1'
MAX_BYTES = int(os.getenv('AI_INVENTORY_MAX_BYTES', 10 * 1024 * 1024))
MAX_ROWS = int(os.getenv('AI_INVENTORY_MAX_ROWS', 10000))
DATA_DIR = Path(os.getenv('AI_INVENTORY_DATA_DIR', './data'))
FIELDS = dict(zip([f'Q{i}' for i in range(1, 24)], [
    'application_id', 'system_name', 'business_purpose', 'business_functions',
    'impact', 'business_owner_email', 'technical_owner_email', 'vendor_owner',
    'ai_source', 'ai_types', 'ml_dl_count', 'llm_count', 'data_types',
    'data_environments', 'deployment_environment', 'deployment_status',
    'go_live_date', 'lines_of_business', 'states', 'risk_tier', 'human_oversight',
    'submitter_name', 'submitted_date']))
LABELS = dict(zip(FIELDS.values(), [
    'Application / System ID', 'AI System / Solution Name', 'Business Purpose / Intended Use',
    'Business Function', 'Impact from AI (Patient/Member, Regulatory, Financial)', 'Business Owner', 'Technical Owner', 'Vendor Owner',
    'Source of AI System', 'Type(s) of AI Used', 'ML/DL Models Count', 'LLM Count',
    'Data Input to or Processed by AI Tool', 'Data Environment', 'Deployment Environment', 'Deployment Status',
    'Go-Live Date', 'LOB', 'State', 'Risk Tier', 'Human-in-the-Loop',
    'Submitter Name', 'Date Submitted']))
INVENTORY_FIELDS = list(FIELDS.values())
HEADERS = [LABELS[field] for field in INVENTORY_FIELDS]
# The explicitly supported Centene export; the two metadata columns are preserved.
EXPORT_COLUMNS = {
    'AI System ID':'application_id', 'Lifecycle':None,
    'AI System / Solution Name':'system_name', 'User AIS':None,
    'Business Purpose':'business_purpose', 'Business Function':'business_functions',
    'AI Impact':'impact', 'Business Owner':'business_owner_email',
    'Technical Owner':'technical_owner_email', 'Vendor Owner':'vendor_owner',
    'AI Source':'ai_source', 'Type(s) of AI Used':'ai_types',
    'ML Models Count':'ml_dl_count', 'LLM Count':'llm_count',
    'AI Data Inputs':'data_types', 'Data Env':'data_environments',
    'Deploy Env':'deployment_environment', 'Deploy Status':'deployment_status',
    'Go-Live Date':'go_live_date', 'LOB':'lines_of_business', 'State':'states',
    'Risk Tier':'risk_tier', 'HITL & Override':'human_oversight',
    'Submitter Name':'submitter_name', 'Survey Rcvd':'submitted_date',
}
INPUT_LAYOUTS = {
    'inventory-template':{LABELS[field]:field for field in INVENTORY_FIELDS},
    'inventory-template-with-lifecycle':{
        **{LABELS[field]:field for field in INVENTORY_FIELDS}, 'Lifecycle':None},
    'centene-export':EXPORT_COLUMNS,
}
MULTI = {'business_functions', 'ai_types', 'data_types', 'data_environments', 'lines_of_business', 'states'}
COUNTS = {'ml_dl_count', 'llm_count'}
DATES = {'go_live_date', 'submitted_date'}
REQUIRED = {FIELDS[f'Q{i}'] for i in [*range(1,8),9,10,*range(13,17),*range(18,24)]}
OPTIONS = {
 'deployment_status': ['Plan & Design','POC','Development','Pilot','Active','Suspended','Sunsetting','Retired'],
 'ai_source': ['Developed in-house','Custom-built by third-party vendor for Centene','Licensed from third-party vendor (customized)','Purchased off-the-shelf (no modifications)','Hybrid (in-house + vendor components)','Other','Unknown'],
 'ai_types': ['Agentic AI','Generative AI (GenAI)','Large Language Model (LLM)','Deep Learning (DL)','Machine Learning (ML)','Predictive Analytics','Robotic Process Automation (RPA)','Rule-Based / Expert System','Other','Unknown'],
 'lines_of_business': ['Medicaid','Medicare','Marketplace','Commercial','Employer Groups','Pharmacy','None','Other'],
 'risk_tier': ['Low','Medium','High','Unknown'],
 'human_oversight': ['Yes','Partially','No','Other','Unknown'],
 'business_functions': ['Claims Processing','Prior Authorization','Utilization Management','Risk Adjustment','Member Engagement','Population Analytics','Quality Measurement / Star Ratings','Fraud, Waste, & Abuse Detection','Clinical Decision Support','Chart Reviews','Enrollment','Network Adequacy','Administrative / Back Office','Care Management','Customer Service','Pharmacy Services','Human Resources','Legal & Regulatory','Financial Operations','Software / Application / Infrastructure Development','Other'],
 'data_types': ['Contains PHI','Contains PII','Case management data','Claims data','Clinical or electronic health record data','External benchmark or reference datasets','Lab or diagnostic data','Member demographic data','Pharmacy data','Provider data','Social determinants of health data','Utilization management data','HR data','Company financial data','Benefit data','Health plan data','Customer Service data','Other'],
 'data_environments': ['Snowflake','Teradata','AWS Redshift','Folder on SharePoint','Folder on employee laptop','Attachment/PDF','Databricks','EMR','GitLab','Oracle','Website or Public Domain','Microsoft 365','Other'],
 'deployment_environment': ['Centene Cloud (AWS, Azure) account','Databricks','External to Centene in vendor cloud environment','Employee laptop','On-prem','Other'],
}
STATE_CODES = dict(zip(
 'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split(),
 'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia'.split('|')))
OPTIONS['states'] = [*STATE_CODES.values(), 'All States', 'None']
# These acquisition choices explicitly establish vendor involvement. Platform
# names and uncertain free-text responses do not establish this condition.
VENDOR_SOURCES = {
    'Custom-built by third-party vendor for Centene',
    'Licensed from third-party vendor (customized)',
    'Purchased off-the-shelf (no modifications)',
    'Hybrid (in-house + vendor components)',
}
ALIASES = {
 'ai_source': {
  'Developed in house':'Developed in-house', 'In-house':'Developed in-house',
  'Vendor built':'Custom-built by third-party vendor for Centene',
  'Vendor-built':'Custom-built by third-party vendor for Centene',
  'Licensed from vendor':'Licensed from third-party vendor (customized)',
  'Off-the-shelf':'Purchased off-the-shelf (no modifications)',
  'Hybrid':'Hybrid (in-house + vendor components)'},
 'ai_types': {'LLM':'Large Language Model (LLM)','ML':'Machine Learning (ML)','DL':'Deep Learning (DL)','GenAI':'Generative AI (GenAI)','RPA':'Robotic Process Automation (RPA)'},
 'lines_of_business': {'Employer Group':'Employer Groups'},
 'states': {**STATE_CODES, 'All':'All States', 'None (Internal or Enterprise-Wide Functions)':'None', 'None (Internal / Enterprise-Wide Functions)':'None'},
 'business_functions': {'Quality Measurement / Stars Ratings':'Quality Measurement / Star Ratings','Human Resources (HR)':'Human Resources'},
 'data_types': {'Provider data (e.g., provider directories, credentialing data)':'Provider data'},
 'data_environments': {'Electronic Medical Record (EMR)':'EMR'},
 'deployment_environment': {
  'On-premise':'On-prem', 'On-premises':'On-prem',
  'External to Centene in Vendor cloud environment (e.g. Harvey AI runs in vendor AWS account)':'External to Centene in vendor cloud environment',
  'External to Centene in Vendor cloud environment (e.g., Harvey AI runs in vendor AWS account)':'External to Centene in vendor cloud environment'},
 'human_oversight': {'Yes—at all stages':'Yes','Yes—at final stage':'Partially','Conditional':'Partially','Yes (all stages)':'Yes','Yes (final decision only)':'Partially','Conditional (exception)':'Partially','Conditional (exception threshold)':'Partially','No (fully autonomous)':'No'},
}
# Cell aliases are independent of the supported column layouts.
ALIASES['ai_types']['Generative AI'] = 'Generative AI (GenAI)'
PLACEHOLDERS = {'','n/a','na','none','null','unknown','not available','not provided','no data provided','tbd'}
FIELD_DESCRIPTIONS = {
    'application_id':'The identifier of the application or AI system. Not Available and Unknown are accepted when the ID is unavailable.',
    'system_name':'The actual name of the AI system or solution.',
    'business_purpose':'What the system does, who it serves, and why it is used.',
    'business_owner_email':'The person accountable for business use. A name or valid email from any domain is accepted, with optional roles, notes or multiple contacts.',
    'technical_owner_email':'The person accountable for technical operation. A name or valid email from any domain is accepted, with optional roles, notes or multiple contacts.',
    'vendor_owner':'The vendor contact’s name or email, required when the source identifies a vendor-built, licensed, purchased or hybrid solution.',
    'ai_source':'How the system was acquired or developed. A platform name alone does not establish vendor involvement.',
    'ai_types':'The AI technologies the system actually uses.',
    'llm_count':'The number of large language models used. A model name or response mode is not a count.',
    'ml_dl_count':'The number of machine-learning or deep-learning models, excluding large language models.',
    'impact':'The combined impact profile. The original selection or description is accepted.',
    'deployment_status':'The current inventory lifecycle stage. Available alone does not establish that the system is Active.',
    'go_live_date':'The actual or planned go-live date. Future dates are accepted. Required when Deployment Status is Active.',
    'lines_of_business':'Lines of business where this system is used. An owner’s organizational LOB may mean something different.',
    'states':'The jurisdictions where the system is used. An owner’s market is not automatically the usage jurisdiction.',
    'submitted_date':'The date this inventory information was submitted.',
    'submitter_name':'The name of the person supplying the inventory information.',
}
FIELD_EXAMPLES = {
    'application_id':'APP-001', 'system_name':'Claims reference assistant',
    'business_purpose':'Helps claims staff find approved internal guidance.',
    'business_owner_email':'Alex Smith <alex.smith@centene.com> — Operations',
    'technical_owner_email':'taylor.jones@centene.com',
    'vendor_owner':'Example Vendor — Alex Smith',
    'llm_count':'0, 1, 2 or Unknown', 'ml_dl_count':'0, 1, 2 or Unknown',
    'impact':'Member: No; Regulatory: No; Financial: Yes',
    'go_live_date':'2026-01-02', 'submitted_date':'2026-09-01',
    'submitter_name':'Alex Smith',
}

def field_definition(field):
    if field in {'technical_owner_email','business_owner_email'}:
        format_hint='An owner name or valid email address from any domain. Multiple contacts and surrounding notes are accepted.'
    elif field == 'application_id':
        format_hint='A unique application ID, or Not Available / Unknown when the ID is unavailable.'
    elif field in COUNTS:
        format_hint='A whole number of 0 or greater, optionally followed by notes such as 2 (production models). ML/DL requires at least 1 when ML, DL or Predictive Analytics is selected. LLM Count allows 0. Blank, Unknown and Not Applicable are accepted when that count is not required. Model names alone are not counts.'
    elif field in DATES:
        format_hint='YYYY-MM-DD, M/D/YYYY, or M/D/YY. Slash dates use month/day order.'
    elif field == 'impact':
        format_hint='A nonblank combined impact profile or description. No fixed wording is required.'
    elif field in MULTI:
        format_hint='At least one selection or description. Separate selections with semicolons or commas. Values outside the examples are accepted.'
    elif field == 'deployment_status':
        format_hint='One current status. Descriptive wording is accepted.'
    elif field in OPTIONS:
        format_hint='A nonblank selection or description. Values outside the examples are accepted.'
    else:
        format_hint='A nonblank value.'
    return {'id':field,'label':LABELS[field],'required':field in REQUIRED,
            'description':FIELD_DESCRIPTIONS.get(field,'Identify the '+LABELS[field].lower()+' for this system.'),
            'format':format_hint,'example':FIELD_EXAMPLES.get(field,''),
            'options':OPTIONS.get(field,[]),'aliases':ALIASES.get(field,{})}
