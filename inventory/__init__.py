"""Small, explicit MVP dictionaries; no inferred source options."""
import os
from pathlib import Path

RULES_VERSION = '2.0'
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
LABELS['response_id'] = 'Response ID'
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
WARNING_RULES = {'APP-01','EMAIL-02','VENDOR-02','COUNT-04','COUNT-05','COUNT-06','DATE-03','HITL-02'}
RULE_SEVERITIES = {r: ('WARNING' if r in WARNING_RULES else 'ERROR') for r in [
 'ID-01','ID-02','REQ-01','ENUM-01','TEXT-01','APP-01','EMAIL-01','EMAIL-02','VENDOR-01','VENDOR-02',
 *[f'COUNT-0{i}' for i in range(1,7)],'DATE-01','DATE-02','DATE-03','SCOPE-01','SCOPE-02','IMPACT-01','RISK-01','HITL-01','HITL-02',
 ]}
# The same rule can accept explicitly unknown information with a warning.
UNKNOWN_SEVERITIES = {rule:'WARNING' for rule in ['ENUM-01','IMPACT-01','RISK-01','HITL-01']}

# Raw agent exports have their own contract; no organization-to-purpose inference.
AGENT_HEADERS = {
    'Name':'system_name', 'Title ID':'response_id', 'Status':'deployment_status',
    'Date created':'created_date', 'Last Modified':'modified_date',
    'Publisher':'technical_owner_email', 'Description':'business_purpose',
    'Instructions':'instructions', 'Platform':'platform', 'Owner':'business_owner_email',
    'Market Name':'market', 'Line of Business Name':'organization_lob',
    'Department Name':'department', 'Job Title':'job_title',
    'Business Function':'business_functions',
    'Impact from AI (Patient/Member, Regulatory, Financial)':'impact',
    'Vendor Owner':'vendor_owner', 'Type(s) of AI used':'ai_types',
    'ML/DL Models Count':'ml_dl_count', 'LLM Count':'llm_count',
    'Data input to or processed by AI tool':'data_types', 'Data Environment':'data_environments',
    'Deployment Environment':'deployment_environment', 'State':'states',
    'Risk Tier':'risk_tier', 'Human-in-the-Loop & Override Capability':'human_oversight',
}
AGENT_OPTIONAL = {'Source of AI System':'ai_source','Go-Live Date':'go_live_date','LOB':'lines_of_business'}
AGENT_LABELS = {field:header for header,field in AGENT_HEADERS.items()}
AGENT_LABELS.update({'ai_source':'Source of AI System','go_live_date':'Go-Live Date','lines_of_business':'Usage line of business'})
ALIASES['ai_types']['Generative AI'] = 'Generative AI (GenAI)'
RULE_SEVERITIES.update({'REQ-02':'ERROR','NAME-01':'WARNING','GAP-01':'WARNING','META-01':'WARNING','DATE-04':'ERROR','LENGTH-01':'WARNING','FORMULA-01':'ERROR'})
RULE_TITLES = {
    'ID-01':'Missing or duplicate record ID','ID-02':'Duplicate application ID',
    'REQ-01':'Required value missing','REQ-02':'Placeholder value','TEXT-01':'Test or generic text',
    'ENUM-01':'Unsupported category','APP-01':'Application ID unavailable',
    'EMAIL-01':'Invalid owner email','EMAIL-02':'External owner email',
    'VENDOR-01':'Vendor contact required','VENDOR-02':'Vendor applicability unresolved',
    'COUNT-01':'Invalid model count','COUNT-02':'LLM count required','COUNT-03':'ML/DL count required',
    'COUNT-04':'Model count unresolved','COUNT-05':'Count and technology mismatch','COUNT-06':'Unknown model count',
    'DATE-01':'Invalid or missing date','DATE-02':'Active system needs go-live date',
    'DATE-03':'Future planned date','DATE-04':'Source date ordering',
    'SCOPE-01':'Conflicting selections','SCOPE-02':'Medicaid jurisdiction missing',
    'IMPACT-01':'Impact incomplete','RISK-01':'Risk tier unresolved','HITL-01':'Oversight unresolved',
    'HITL-02':'Override unresolved','NAME-01':'Repeated system name','GAP-01':'Source mapping unavailable',
    'META-01':'Organization metadata missing','LENGTH-01':'Possible truncated instructions','FORMULA-01':'Formula in source',
}
PLACEHOLDERS = {'','n/a','na','none','null','unknown','not available','not provided','no data provided','tbd'}

def field_rules(field, profile):
    rules = {
        'response_id':'A meaningful record ID is required. Repeated IDs flag every affected record.',
        'application_id':'Required. Not Available and Unknown require review. Other IDs must be unique in the upload.',
        'system_name':'Required. Reject test-only, numeric, and generic names. Repeated names require review.',
        'business_purpose':'Required. Reject test-only and placeholder descriptions; legitimate descriptions of testing are allowed.',
        'business_owner_email':'Required. Forms: exactly one valid email; external domains require review. Agent export: a meaningful Owner value.',
        'technical_owner_email':'Required. Forms: exactly one valid email; external domains require review. Agent export: a meaningful Publisher value.',
        'vendor_owner':'Vendor-based acquisition requires a meaningful contact. Missing acquisition metadata leaves applicability unresolved.',
        'ml_dl_count':'Nonnegative whole number. Explicit ML/DL requires a positive count. Blank is not zero; Unknown requires review.',
        'llm_count':'Nonnegative whole number. Explicit LLM requires a positive count. Names and response modes are not counts.',
        'impact':'Member, Regulatory, and Financial must each appear exactly once as Yes, No, or Unknown. Unknown requires review.',
        'go_live_date':'A valid date. Active systems require a nonfuture date. Never substitute the creation date. Missing agent-export metadata requires review.',
        'submitted_date':'Required valid date, no later than the validation date.',
        'submitter_name':'Required meaningful name; placeholder values fail.',
        'created_date':'Required ISO date/timestamp, no later than the validation date.',
        'modified_date':'Required ISO date/timestamp, no earlier than creation and no later than the validation date.',
        'instructions':'Missing instructions require review. Exactly 8,000 characters flags possible truncation, not a confirmed error.',
        'platform':'A meaningful source platform is required; it does not establish acquisition type.',
    }
    if field in rules: return rules[field]
    if field in {'market','organization_lob','department','job_title'}:
        return 'Missing or placeholder organization metadata requires review. It is not used to infer system purpose, function, or usage geography.'
    if field in OPTIONS:
        value='Use configured categories: '+', '.join(OPTIONS[field])+'.'
        if 'Other' in OPTIONS[field]: value+=' Other requires a description.'
        if field in {'risk_tier','human_oversight','ai_types','ai_source'}: value+=' Unknown requires review.'
        if field in {'states','lines_of_business'}: value+=' None must stand alone; All States must stand alone. Medicaid requires a jurisdiction.'
        if field=='deployment_status': value+=' Available in an agent export requires a lifecycle mapping; it is not automatically Active.'
        if profile=='agents' and field in {'ai_source','lines_of_business'}: value+=' Missing source metadata requires review; no inferred value is substituted.'
        return value
    return 'Retained source metadata; no validation rule is configured.'
