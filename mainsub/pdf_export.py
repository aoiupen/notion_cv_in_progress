from fpdf import FPDF

def get_output_pdf_name(doc_type, language, page_rule=None, expanded=False):
    # doc_type: 'cv' or 'pf'
    # language: 'ko' or 'en'
    # page_rule: None, 'rule1', 'rule2', ...
    # expanded: True(펼친 것), False(기본)
    
    lang_str = 'ko' if language == 'ko' else 'en'
    type_str = 'cv' if doc_type == 'resume' else 'pf'
    rule_str = ''
    if page_rule and page_rule != 'none':
        rule_str = f'_pr{page_rule}'
    expanded_str = '_e' if expanded else '_b'
    filename = f"{lang_str}_{type_str}{rule_str}{expanded_str}.pdf"
    return filename


def export(resume_data, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="이력서", ln=True, align='C')
    for key, value in resume_data.items():
        pdf.cell(200, 10, txt=f"{key}: {value}", ln=True)
    pdf.output(filename) 