import re
from pathlib import Path
import io

EMAIL=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE=re.compile(r"(?:\+?\d[\d .()/-]{7,}\d)")
DATE=re.compile(r"\b(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)[ ./-]+\d{4}|\d{1,2}[/-](?:19|20)?\d{2}|(?:19|20)\d{2}|présent|actuellement|aujourd'hui|present|current)\b",re.I)
SKILLS=["cost reduction","cost saving","réduction des coûts","value analysis","analyse de la valeur","value engineering","ingénierie de la valeur","automotive","automobile","mobility","mobilité","mechatronic","mécatronique","vehicle subsystem","sous-système véhicule","apqp","ppap","dfmea","dvp&r","project management","gestion de projet","purchasing","achats","supplier","fournisseur","excel","plm","ebom","mbom","bom","nomenclature","cad","cao","product specification","spécifications produit","data analysis","analyse de données","negotiation","négociation","problem solving","résolution de problèmes","cross-functional","coordination transverse","communication","autonomy","autonomie","proactivity","proactivité","catia","teamcenter","enovia","solidworks","power bi","sap","nx","led","photométrie","photometry","lin","can","cem","emc"]
LANGUAGE_ALIASES={"French":["french","français","française"],"English":["english","anglais","anglaise"],"Arabic":["arabic","arabe"],"Spanish":["spanish","espagnol","espagnole"],"German":["german","allemand","allemande","deutsch"],"Italian":["italian","italien","italienne"]}
SECTION_GROUPS={
    "education":["education","formation","formation académique","formation et diplômes","diplômes et formations","diplôme","diplômes","études","études et diplômes"],
    "experience":["professional experience","work experience","career history","experience","expérience professionnelle","expériences professionnelles","expérience","expériences","parcours professionnel","parcours professionnel et stages","expériences professionnelles et stages"],
    "projects":["projects","project experience","projets","projets académiques"],
    "skills":["skills","technical skills","competencies","compétences","compétences techniques","compétences clés","savoir-faire","expertises","expertises techniques et métier"],
    "languages":["languages","langues","langues parlées","compétences linguistiques"],
    "certifications":["certifications","certificates","certificats","certifications et formations"],
    "software":["software","tools","logiciels","outils","outils informatiques","environnements logiciels"],
    "soft_skills":["soft skills","savoir-être","compétences comportementales","qualités personnelles","qualités"],
    "profile":["profile","summary","professional summary","profil","profil recherché","résumé","à propos","accroche professionnelle"],
}
_SECTION_ALTERNATION="|".join(re.escape(label) for labels in SECTION_GROUPS.values() for label in sorted(labels,key=len,reverse=True))
SECTION_LINE=re.compile(r"(?i)^\s*("+_SECTION_ALTERNATION+r")\s*(?::\s*(.*))?\s*$")

def _possible_multicolumn(blocks: list, page_width: float) -> bool:
    text_blocks=[b for b in blocks if len(str(b[4]).strip())>25 and (b[2]-b[0])<page_width*.58]
    left=[b for b in text_blocks if b[0]<page_width*.48 and b[2]<page_width*.62]
    right=[b for b in text_blocks if b[0]>page_width*.42 and b[2]>page_width*.50]
    if len(left)<2 or len(right)<2: return False
    return any(min(a[3],b[3])-max(a[1],b[1])>12 for a in left for b in right)

def _section_key(label: str) -> str:
    normalized=label.casefold().strip()
    return next((key for key,labels in SECTION_GROUPS.items() if normalized in labels),normalized)

def parse_resume(filename: str, data: bytes, enable_ocr: bool = False) -> dict:
    ext=Path(filename).suffix.lower(); meta={"pages":None,"hidden_text_suspected":False,"scanned_pages":[],"ocr_pages":[],"multicolumn_pages":[],"ocr_attempted":False,"ocr_error":None}
    raw_segments=[]
    if ext==".pdf":
        import fitz
        doc=fitz.open(stream=data,filetype="pdf"); chunks=[]
        for page_index,page in enumerate(doc,1):
            blocks=page.get_text("blocks",sort=True)
            page_text="\n".join(str(b[4]) for b in blocks)
            image_present=bool(page.get_images(full=True))
            if _possible_multicolumn(blocks,page.rect.width): meta["multicolumn_pages"].append(page_index)
            page_word_count=len(re.findall(r"\b\w+\b",page_text))
            if image_present and page_word_count<25:
                meta["scanned_pages"].append(page_index)
                if enable_ocr:
                    meta["ocr_attempted"]=True
                    try:
                        text_page=page.get_textpage_ocr(language="fra+eng",dpi=200,full=True)
                        ocr_blocks=page.get_text("blocks",textpage=text_page,sort=True)
                        ocr_text="\n".join(str(b[4]) for b in ocr_blocks)
                        if len(ocr_text.strip())>len(page_text.strip()):
                            page_text=ocr_text; blocks=ocr_blocks; meta["ocr_pages"].append(page_index)
                    except Exception as exc:
                        meta["ocr_error"]=str(exc)
            chunks.append(page_text)
            for line in page_text.splitlines():
                if line.strip(): raw_segments.append({"source":f"Page {page_index}"+(" (OCR)" if page_index in meta["ocr_pages"] else ""),"text":line.strip()})
            try:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines",[]):
                        for span in line.get("spans",[]):
                            if span.get("text","").strip() and (span.get("alpha",255)==0 or (span.get("flags",0)&3)==3): meta["hidden_text_suspected"]=True
            except Exception: pass
        text="\n".join(chunks); meta["pages"]=len(doc)
    elif ext==".docx":
        from docx import Document
        from docx.oxml.text.paragraph import CT_P
        from docx.oxml.table import CT_Tbl
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        doc=Document(io.BytesIO(data)); parts=[]; paragraph_index=0; table_index=0
        for element in doc.element.body.iterchildren():
            if isinstance(element,CT_P):
                paragraph_index+=1; paragraph=Paragraph(element,doc); parts.append(paragraph.text)
                if paragraph.text.strip(): raw_segments.append({"source":f"Paragraph {paragraph_index}","text":paragraph.text.strip()})
            elif isinstance(element,CT_Tbl):
                table_index+=1; table=Table(element,doc)
                for row_index,row in enumerate(table.rows,1):
                    row_text=" | ".join(c.text for c in row.cells)
                    parts.append(row_text)
                    if row_text.strip(): raw_segments.append({"source":f"Table {table_index}, row {row_index}","text":row_text.strip()})
        meta["docx_tables"]=table_index
        text="\n".join(parts)
    else: raise ValueError("Upload a PDF or DOCX file.")
    text=re.sub(r"[ \t]+"," ",text).strip(); words=re.findall(r"\b[\w@.+/-]+\b",text)
    emails=list(dict.fromkeys(EMAIL.findall(text))); phones=list(dict.fromkeys(m.group(0).strip() for m in PHONE.finditer(text)))
    lines=[re.sub(r"\s+"," ",x).strip(" |•-") for x in text.splitlines() if x.strip()]
    evidence_segments=[]; active_section=None; section_lines={}
    for segment in raw_segments:
        line=re.sub(r"\s+"," ",segment["text"]).strip(" |•-")
        if not line: continue
        heading=SECTION_LINE.match(line)
        if heading:
            active_section=_section_key(heading.group(1))
            line=(heading.group(2) or "").strip()
            if not line: continue
        if active_section: section_lines.setdefault(active_section,[]).append(line)
        evidence_segments.append({"source":segment["source"],"section":active_section or "Section not detected","text":line})
    sections={key:"\n".join(content) for key,content in section_lines.items()}
    headings={"curriculum vitae","resume","cv","profile","summary","contact","curriculum vitae","profil","à propos","contact"}
    name=next((x for x in lines[:8] if 1<len(x.split())<=4 and len(x)<60 and x.casefold() not in headings and not EMAIL.search(x) and not any(c.isdigit() for c in x)),"")
    skill_hits=[s for s in SKILLS if re.search(r"(?i)\b"+re.escape(s)+r"\b",text)]
    languages=[canonical for canonical,aliases in LANGUAGE_ALIASES.items() if any(re.search(r"(?i)\b"+re.escape(alias)+r"\b",text) for alias in aliases)]
    education=sections.get("education","")
    experience=sections.get("experience","")
    certifications=sections.get("certifications","")
    software=sections.get("software","")
    soft_skills=sections.get("soft_skills","")
    warning=bool(text) and len(words)<15
    warnings=[]
    if not text: warnings.append("No selectable text found. This PDF may be scanned or empty.")
    elif len(words)<15: warnings.append("Very little text extracted; check for a scanned PDF or extraction failure.")
    if meta["scanned_pages"]:
        page_list=", ".join(str(n) for n in meta["scanned_pages"])
        if meta["ocr_pages"]:
            warnings.append(f"OCR was applied to scanned page(s) {', '.join(str(n) for n in meta['ocr_pages'])}. OCR can misread names, dates, and technical terms; check those pages against the original.")
        elif enable_ocr and meta["ocr_error"]:
            warnings.append(f"OCR was requested for scanned page(s) {page_list} but could not run. Install Tesseract OCR with French and English language data. Detail: {meta['ocr_error'][:180]}")
        else:
            warnings.append(f"Image-based or scanned content was detected on page(s) {page_list}; it may not be included in extracted text. Use ‘Try OCR’ if Tesseract with French and English language data is installed.")
    if meta["multicolumn_pages"]:
        page_list=", ".join(str(n) for n in meta["multicolumn_pages"])
        warnings.append(f"Possible multi-column layout detected on page(s) {page_list}. Reading order may be interleaved; review the extracted text and original pages.")
    if meta.get("docx_tables",0):
        warnings.append("DOCX tables were extracted in document order. Text in side-by-side cells or merged layouts may not read naturally; compare with the original preview.")
    if not emails: warnings.append("No email address detected.")
    if not phones: warnings.append("No phone number detected.")
    if warning: warnings.append("Reading order or extraction may be incomplete. Review the extracted text before relying on matches.")
    if meta["hidden_text_suspected"]: warnings.append("Potential invisible or suspicious PDF text detected; inspect the source.")
    return {"filename":filename,"text":text,"evidence_segments":evidence_segments,"word_count":len(words),"name_suggestion":name,"emails":emails,"phones":phones,"education":education,"experience":experience,"certifications":certifications,"software":software,"soft_skills":soft_skills,"languages":languages,"language_details":sections.get("languages",""),"skills":skill_hits,"dates":list(dict.fromkeys(DATE.findall(text))),"sections":sections,"metadata":meta,"warnings":warnings}
