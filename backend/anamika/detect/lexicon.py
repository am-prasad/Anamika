"""Static vocabularies: labels, honorifics, relations, facility and clinical words.

These encode *structure* of Indian clinical records (how names are introduced, how
relatives are marked, which words are clinical), never specific people. Patient names
are learned at run time from the input itself (:mod:`anamika.detect.runtime`).
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- name structure

#: tokens that never identify anyone on their own (scorer's "generic name parts")
GENERIC_NAME_TOKENS = frozenset("""
devi kumar kumari kr md mohd mohammad muhammad mohammed ji sahab saab sahib smt shri sri shree
mr mrs ms miss km baby master didi bhai bhaiya behen behenji bibi begum bai ben bano
late sh dr
देवी कुमार कुमारी जी साहब श्री श्रीमती मो मोहम्मद बेगम बानो बाई
""".split())

#: titles that precede a person's name
PRE_TITLES = r"(?:Mr|Mrs|Ms|Smt|Shri|Sri|Shree|Km|Kumari|Master|Baby|Md|Mohd|Late|Sh|Kum)"
PRE_TITLES_DEVA = r"(?:श्रीमती|श्री|कुमारी|सुश्री|स्व\.?|मो\.?)"

#: honorifics that follow a name in Hinglish speech
POST_HONORIFICS = r"(?:ji|jee|sahab|saab|sahib|didi|bhaiya|bhai|aunty|auntie|uncle|amma|behenji|babu|chacha|chachi|dada|dadi|nana|nani|mausi|bua)"
POST_HONORIFICS_DEVA = r"(?:जी|साहब|दीदी|भैया|भाई|अम्मा|बाबू|चाचा|चाची|दादा|दादी)"

#: Hinglish postpositions that follow a person ("Shahid ka BP", "Meera ne dawai li")
HINGLISH_PARTICLES = r"(?:ka|ki|ke|ko|ne|se|kaa|kee)"

#: relation markers that introduce a relative's name. ``H/o`` is excluded on purpose:
#: in clinical notes it means "history of".
RELATION_MARKERS = r"(?:S/O|D/O|W/O|C/O|F/O|M/O|Son\s+of|Daughter\s+of|Wife\s+of|Husband\s+of|Care\s+of)"
RELATION_MARKERS_DEVA = r"(?:पुत्र|पुत्री|पत्नी|पति)"

# --------------------------------------------------------------------------- labels in text

#: labels whose value is the patient's name
PATIENT_NAME_LABELS = (r"(?:Patient(?:'s)?\s+Name|Pt\.?\s*Name|Name\s+of\s+(?:the\s+)?Patient|Patient|Name|Pt\.?|"
                       r"मरीज़?\s+का\s+नाम|रोगी\s+का\s+नाम|नाम)")
#: labels whose value is a relative / attendant / caller
RELATIVE_LABELS = (r"(?:Attendant|Guardian|Father(?:'s)?\s+Name|Husband(?:'s)?\s+Name|Mother(?:'s)?\s+Name|"
                   r"Next\s+of\s+Kin|NOK|Relative|Informant|Spouse|Father/Husband|"
                   r"पिता\s+का\s+नाम|पति\s+का\s+नाम|माता\s+का\s+नाम|परिजन|अटेंडेंट)")
#: free-text phrases that introduce a person ("called by X")
PERSON_VERBS = r"(?:called|witnessed|accompanied|brought|raised|signed|informed|attended|escorted|visited)\s+by\s*:?"
#: labels whose value is a hospital identifier
ID_LABELS = (r"(?:UHID|MRN|MR\s*No|CR\s*No|Reg(?:istration)?\.?\s*No|Regn\.?\s*No|Patient\s*ID|IPD?\s*No|"
             r"IP\s*No|Adm(?:ission)?\.?\s*No|OPD\s*No|Hospital\s*(?:ID|No)|Case\s*No|"
             r"पंजीकरण\s*सं\.?|पंजीकरण\s*संख्या|आईपीडी\s*सं\.?|भर्ती\s*सं\.?)")
INSURANCE_LABELS = r"(?:Policy\s*No|Policy|Insurance\s*(?:ID|No)|Member\s*ID|TPA\s*(?:ID|No)|Card\s*No|PMJAY\s*ID)"
PHONE_LABELS = r"(?:Mob(?:ile)?\.?(?:\s*No)?|Phone|Ph\.?|Contact(?:\s*No)?|Tel\.?|WhatsApp|मोबाइल|फ़ोन|फोन)"
ADDRESS_LABELS = r"(?:Address|Addr\.?|Residence|पता)"
VILLAGE_LABELS = r"(?:Vill(?:age)?\.?|Gram|Gaon|Mohalla|ग्राम|गांव|गाँव|मोहल्ला)"
AGE_LABELS = r"(?:Age(?:/Sex)?|आयु|उम्र)"
#: administrative places that are preserved (district / tehsil are research value)
ADMIN_PLACE_MARKERS = r"(?:Tehsil|Teh\.?|Distt\.?|District|Dist\.?|Jila|Zila|Block|तहसील|जिला|ज़िला)"

#: words that end a name when scanning tokens after a label
NAME_STOPWORDS = frozenset("""
age sex yrs yr years year y m f male female uhid mrn reg regn no ipd ip opd mob mobile phone
date dob address ward bed w s d c o h k s/o d/o w/o c/o ka ki ke ko ne se hai tha thi the
patient name diagnosis admitted discharged in on at of and with for from to is was reviewed
आयु उम्र वर्ष पुरुष महिला का की के को ने से है था थी पता मोबाइल तारीख पंजीकरण
""".split())

#: facility words: a capitalised phrase ending in one of these is an institution (kept)
FACILITY_WORDS = (r"(?:Hospital|Hospitals|Sadan|Multispeciality|Multi-?speciality|Charitable|Clinic|Nursing\s+Home|"
                  r"Pathology|Diagnostics?|Labs?|Laboratory|Medical\s+College|Trust|Kendra|Centre|Center|"
                  r"Institute|Dispensary|PHC|CHC|Health\s+Centre|Pharmacy|Chikitsalaya|Aspatal|"
                  r"अस्पताल|चिकित्सालय)")

MONTHS = ("january february march april may june july august september october november december "
          "jan feb mar apr jun jul aug sep sept oct nov dec").split()

#: clinical / document vocabulary that can be Title-cased but is never a name
CLINICAL_WORDS = frozenset("""
tab cap inj syp syr inh oint drop drops tablet capsule injection syrup inhaler ointment cream gel
paracetamol dolo crocin calpol pan pantoprazole rabeprazole omeprazole ranitidine famotidine
amlodipine telmisartan telma losartan ramipril enalapril atenolol metoprolol metformin glimepiride
gliclazide insulin levothyroxine thyronorm atorvastatin rosuvastatin aspirin ecosprin clopidogrel
ceftriaxone cefixime amoxicillin augmentin azithromycin doxycycline ciprofloxacin ofloxacin
metronidazole rifampicin isoniazid pyrazinamide ethambutol salbutamol budesonide montelukast
cetirizine levocetirizine ondansetron domperidone furosemide spironolactone prednisolone
dexamethasone hydrocortisone diclofenac ibuprofen tramadol vitamin calcium iron folic zinc ors
haemoglobin hemoglobin random blood sugar serum creatinine urea sodium potassium total wbc count
platelet platelets bilirubin sgot sgpt alt ast albumin protein glucose fasting hba1c tsh lipid
cholesterol triglycerides hdl ldl esr crp ns1 antigen igm igg widal dengue malaria typhoid
tuberculosis tb covid hiv hbsag hcv urine culture xray x-ray ecg echo usg ct mri
fever pain cough cold vomiting diarrhoea diarrhea weakness breathlessness headache abdomen chest
hypertension diabetes asthma copd pneumonia anaemia anemia sepsis jaundice hepatitis nephropathy
disease syndrome disorder infection fracture injury surgery section caesarean cataract
phacoemulsification haemodialysis hemodialysis dialysis appendicectomy cholecystectomy hernia
parkinson parkinson's alzheimer alzheimer's crohn crohn's addison addison's cushing cushing's graves
wilson wilson's hodgkin hodgkin's down bell bell's kawasaki guillain barre barré
medicine surgery paediatrics pediatrics gynaecology obstetrics orthopaedics orthopedics
cardiology neurology nephrology pulmonology gastroenterology dermatology psychiatry ent ophthalmology
oncology urology emergency icu nicu picu ot opd ipd ward bed general private semi
discharge summary admission diagnosis history course advice medications prescription report
nursing notes note visit review follow up followup plan impression findings investigation
investigations procedure treatment condition stable improved referred death expired lama
routine panel test result unit range reference normal high low positive negative
morning evening night today tomorrow yesterday daily weekly monthly
consultant doctor dr nurse sister staff attendant patient visitor log export system module records
hospital clinic lab laboratory pathology diagnostics centre center sadan charitable trust
multispeciality district medical college government govt private limited ltd pvt
india uttar pradesh up lucknow kanpur
dear sir madam regards thanks please kindly
the and of in on at to for with by from as is was be not no yes ok
""".split())

_TITLE_TOKEN = re.compile(r"^[A-Z][a-z'’]+$|^[A-Z]{2,}$")


def is_titleish(tok: str) -> bool:
    """``Ramesh`` or ``RAMESH`` (a token that *could* be a capitalised name)."""
    return bool(_TITLE_TOKEN.match(tok))
