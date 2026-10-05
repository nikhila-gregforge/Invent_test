"""Inventory contract and optional header suggestions; upload names do not set policy."""
import os
from pathlib import Path

RULES_VERSION = '3.0'
MAX_BYTES = int(os.getenv('AI_INVENTORY_MAX_BYTES', 10 * 1024 * 1024))
MAX_ROWS = int(os.getenv('AI_INVENTORY_MAX_ROWS', 10000))
DATA_DIR = Path(os.getenv('AI_INVENTORY_DATA_DIR', './data'))
RECOGNIZED_DOMAINS = {'centene.com'}
HEADER_ALIASES = {'ID': ['ID'],
 'Q1': ["Provide the Application ID / System ID. If not available or unknown, please enter 'Not Available'."],
 'Q2': ['Provide the official name of the AI System / Solution Name'],
 'Q3': ['Business Purpose: Describe the primary business purpose of the AI system'],
 'Q4': ['Business Function: Select the primary business function from the list below. If multiple apply, '
        'select the primary function.'],
 'Q5': ['Impact from AI (Patient/Member, Regulatory, Financial): Select the combined impact profile'],
 'Q6': ['Business Owner: Enter one Centene email address for the accountable individual.'],
 'Q7': ['Technical Owner: Enter one Centene email address for the accountable individual.'],
 'Q8': ['Vendor Owner: Identify the accountable individual(s).'],
 'Q9': ['Source of AI System: Indicate how the AI solution was acquired or developed.'],
 'Q10': ['Type(s) of AI used: Select the primary AI technology type, if multiple select all that are used'],
 'Q11': ['ML/DL Models Count: Enter the number of Machine Learning (ML) and Deep Learning (DL) models used '
         'by the AI System, excluding Large Language Models (LLMs) reported in Question 12. Examples include '
         '...',
         'ML/DL Models Count: Enter the number of Machine Learning (ML) and Deep Learning (DL) models used '
         'by the AI System, excluding Large Language Models (LLMs) reported in Question 12. Examples include '
         'xgbo'],
 'Q12': ['LLM Count: Enter the number of unique Large Language Models (LLMs) used by the AI System. Examples '
         'include GPT-4o, GPT-5, Claude Sonnet, Gemini, Llama models etc. (Do not include LLMs in Question '
         '11).'],
 'Q13': ['Data input to or processed by AI tool: What type of data is being fed to AI?'],
 'Q14': ['Data Environment: Where is data being sourced from?'],
 'Q15': ['Deployment Environment: Where is AI running?'],
 'Q16': ['Deployment Status: Lifecycle Status'],
 'Q17': ['Go-Live Date'],
 'Q18': ['Line of Business: Select all that apply'],
 'Q19': ['State: Enter the states AIS is used in.'],
 'Q20': ['Risk Tier'],
 'Q21': ['Human-in-the-Loop: Is there human oversight or review at any stage of the operation of AI system',
         'Human-in-the-Loop & Override Capability: Select the combined Human-in-the-Loop level + Override '
         'capability.'],
 'Q22': ['Submitter Name: Name of the person filling the form.'],
 'Q23': ['Date Submitted']}

FIELDS = dict(zip([f'Q{i}' for i in range(1, 24)], [
    'application_id', 'system_name', 'business_purpose', 'business_functions',
    'impact', 'business_owner_email', 'technical_owner_email', 'vendor_owner',
    'ai_source', 'ai_types', 'ml_dl_count', 'llm_count', 'data_types',
    'data_environments', 'deployment_environment', 'deployment_status',
    'go_live_date', 'lines_of_business', 'states', 'risk_tier', 'human_oversight',
    'submitter_name', 'submitted_date']))
LABELS = dict(zip(FIELDS.values(), [
    'Application / System ID', 'AI System / Solution Name', 'Business Purpose / Intended Use',
    'Business Function', 'Impact from AI', 'Business Owner', 'Technical Owner', 'Vendor Owner',
    'Source of AI System', 'Types of AI Used', 'ML/DL Models Count', 'LLM Count',
    'Data Input / Processed', 'Data Environment', 'Deployment Environment', 'Deployment Status',
    'Go-Live Date', 'Line of Business', 'State', 'Risk Tier', 'Human-in-the-Loop',
    'Submitter Name', 'Date Submitted']))
LABELS['override_capability'] = 'Override capability'
LABELS['response_id'] = 'Source record ID'
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
ALIASES = {
 'ai_types': {'LLM':'Large Language Model (LLM)','ML':'Machine Learning (ML)','DL':'Deep Learning (DL)','GenAI':'Generative AI (GenAI)','RPA':'Robotic Process Automation (RPA)'},
 'lines_of_business': {'Employer Group':'Employer Groups'},
 'states': {**STATE_CODES, 'All':'All States', 'None (Internal or Enterprise-Wide Functions)':'None'},
 'business_functions': {'Quality Measurement / Stars Ratings':'Quality Measurement / Star Ratings','Human Resources (HR)':'Human Resources'},
 'deployment_environment': {
  'External to Centene in Vendor cloud environment (e.g. Harvey AI runs in vendor AWS account)':'External to Centene in vendor cloud environment',
  'External to Centene in Vendor cloud environment (e.g., Harvey AI runs in vendor AWS account)':'External to Centene in vendor cloud environment'},
 'human_oversight': {'Yes—at all stages':'Yes','Yes—at final stage':'Partially','Conditional':'Partially','Yes (all stages)':'Yes','Yes (final decision only)':'Partially','Conditional (exception)':'Partially','No (fully autonomous)':'No'},
}
# Header aliases only suggest choices. Every upload requires a confirmed mapping.
ALIASES['ai_types']['Generative AI'] = 'Generative AI (GenAI)'
INVENTORY_FIELDS = [*FIELDS.values(), 'response_id']
SOURCE_ALIASES = {
    'response_id':['ID','Title ID','Record ID'],
    'application_id':['Application ID','System ID'],
    'system_name':['Name','System name','AI system name','AI name'],
    'business_purpose':['Description','Purpose','Intended use'],
    'business_functions':['Business Function'],
    'ai_types':['Type(s) of AI used','AI technology'],
    'data_types':['Data input to or processed by AI tool'],
    'deployment_status':['Status'],
    'lines_of_business':['LOB','Usage line of business'],
    'states':['State'],
    'human_oversight':['Human-in-the-Loop & Override Capability'],
}
# Publisher, Owner, creation dates and organization metadata are intentionally not
# treated as accountable owners, go-live dates or usage scope.
PLACEHOLDERS = {'','n/a','na','none','null','unknown','not available','not provided','no data provided','tbd'}
FIELD_DESCRIPTIONS = {
    'application_id':'The identifier of the application or AI system. Not Available and Unknown require review.',
    'system_name':'The actual name of the AI system or solution.',
    'business_purpose':'What the system does, who it serves, and why it is used.',
    'business_owner_email':'The person accountable for business use: a name (with role or department if useful) or one valid email.',
    'technical_owner_email':'The person accountable for technical operation: a name (with role or department if useful) or one valid email.',
    'vendor_owner':'The accountable vendor contact, when the acquisition involves a vendor.',
    'ai_source':'How the system was acquired or developed. A platform name does not establish this.',
    'ai_types':'The AI technologies the system actually uses.',
    'llm_count':'The number of large language models used. A model name or response mode is not a count.',
    'ml_dl_count':'The number of machine-learning or deep-learning models, excluding large language models.',
    'impact':'State Member, Regulatory and Financial impact separately, using Yes, No or Unknown for each.',
    'deployment_status':'The current inventory lifecycle stage. Available alone does not establish that the system is Active.',
    'go_live_date':'The actual go-live date. Do not substitute a creation or last-modified date.',
    'lines_of_business':'Lines of business where this system is used. An owner’s organizational LOB may mean something different.',
    'states':'The jurisdictions where the system is used. An owner’s market is not automatically the usage jurisdiction.',
    'submitted_date':'The date this inventory information was submitted.',
    'submitter_name':'The name of the person supplying the inventory information.',
    'response_id':'Optional source record identifier for tracing a row back to the uploaded file. Source row numbers are always retained.',
}
FIELD_EXAMPLES = {
    'application_id':'APP-001', 'system_name':'Claims reference assistant',
    'business_purpose':'Helps claims staff find approved internal guidance.',
    'business_owner_email':'Alex Smith, Operations',
    'technical_owner_email':'taylor.jones@centene.com',
    'vendor_owner':'Example Vendor — Alex Smith',
    'llm_count':'0, 1, 2 or Unknown', 'ml_dl_count':'0, 1, 2 or Unknown',
    'impact':'Member: No; Regulatory: No; Financial: Yes',
    'go_live_date':'2026-01-02', 'submitted_date':'2026-09-01',
    'submitter_name':'Alex Smith', 'response_id':'001',
}

def field_definition(field):
    if field in {'business_owner_email','technical_owner_email'}:
        format_hint='A person’s name, optionally with role or department, or exactly one valid email address.'
    elif field == 'application_id':
        format_hint='The application ID. Not Available or Unknown is accepted with a warning.'
    elif field == 'response_id':
        format_hint='Optional. A supplied identifier must be unique within the file; leading zeros are preserved.'
    elif field in COUNTS:
        format_hint='A whole number of 0 or greater. Blank means not supplied; Unknown requires review. A declared model type requires a positive count.'
    elif field in DATES:
        format_hint='YYYY-MM-DD, M/D/YYYY, M/D/YY, or an Excel date cell. Slash dates use month/day order.'
    elif field == 'impact':
        format_hint='Member: Yes/No/Unknown; Regulatory: Yes/No/Unknown; Financial: Yes/No/Unknown.'
    elif field in MULTI:
        format_hint='Select supported values. Separate multiple selections with semicolons. Use Other: description when applicable.'
    elif field in OPTIONS:
        format_hint='One supported value. Use Other: description when applicable.'
    else:
        format_hint='A meaningful value, not a placeholder.'
    return {'id':field,'label':LABELS[field],'required':field in REQUIRED,
            'description':FIELD_DESCRIPTIONS.get(field,'Identify the '+LABELS[field].lower()+' for this system.'),
            'format':format_hint,'example':FIELD_EXAMPLES.get(field,''),
            'options':OPTIONS.get(field,[]),'aliases':ALIASES.get(field,{})}
