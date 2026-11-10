from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle

def make_report(cv: dict,result: dict) -> bytes:
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=letter,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=40); styles=getSampleStyleSheet(); story=[]
    def p(s,style="BodyText"): story.append(Paragraph(s,styles[style]))
    p("Candidate Job Compatibility Evaluation","Title"); p("Independent ATS simulation evaluation report","Heading2")
    exp=result['experience_relevance']; edu=result['education_compatibility']
    p(f"Candidate: {escape(cv.get('name_suggestion') or 'Not confidently identified')}<br/>Overall compatibility: {result['score']}/100 — {escape(result['band'])}<br/>Technical competency: {result['technical_score']}/100 | Experience relevance: {str(exp)+'/100' if exp is not None else 'not configured'} | Education compatibility: {str(edu)+'/100' if edu is not None else 'not configured'}")
    story.append(Spacer(1,10)); p("A. Candidate profile","Heading2")
    p(f"Email: {escape(', '.join(cv.get('emails',[])) or 'Not detected')}<br/>Phone: {escape(', '.join(cv.get('phones',[])) or 'Not detected')}<br/>Languages: {escape(', '.join(cv.get('languages',[])) or 'Not detected')}<br/>Extracted words: {cv.get('word_count',0)}")
    p("B. CV parsing results","Heading2"); warnings=cv.get("warnings",[])
    p("<br/>".join("• "+escape(w) for w in warnings) if warnings else "No parsing warnings surfaced.")
    p("C–D. Competency matching","Heading2")
    small=ParagraphStyle("EvidenceSmall",parent=styles["BodyText"],fontSize=7.5,leading=9)
    rows=[[Paragraph("Category",small),Paragraph("Weight",small),Paragraph("Classification",small),Paragraph("Supporting excerpt and source",small)]]
    for category,item in result['matches'].items():
        evidence=[]
        for ev in item.get("evidence_details",[]):
            evidence.append(f"<b>{escape(ev['source'])} · {escape(ev['section'])}</b> (source confidence: {escape(ev['source_confidence'])}): {escape(ev['text'])} <i>(matched: {escape(', '.join(ev['matched_terms']))})</i>")
        evidence_html="<br/><br/>".join(evidence) if evidence else "No supporting excerpt found in extracted text."
        rows.append([Paragraph(escape(category),small),Paragraph(f"{item['weight']}%",small),Paragraph(escape(item['level']),small),Paragraph(evidence_html,small)])
    tab=Table(rows,colWidths=[125,42,100,261],repeatRows=1); tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#c7d2df")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#eef3f8")])]))
    story.append(tab)
    p("Qualification requirements entered for this job","Heading2")
    for heading,requirement in result.get("qualifications",{}).items():
        p(f"<b>{escape(heading)}:</b> {escape(requirement)}")
    p("E. Scoring methodology","Heading2"); p("Category weights total 100%. Direct experience receives full category credit; partial practical experience 65%; theoretical knowledge 30%; missing evidence 0%. Up to 10 additional points reflect semantic similarity. Keywords alone cannot establish practical experience.")
    p(f"Keyword coverage: {result['keyword_coverage']['ratio']:.0%} ({len(result['keyword_coverage']['present'])} terms detected). Semantic method: {escape(result['semantic']['method'])}.")
    p("F. Missing and weakly supported requirements","Heading2"); p("Missing: "+escape(", ".join(result['missing']) or "None flagged")+"<br/>Weakly supported: "+escape(", ".join(result['weak']) or "None flagged"))
    p("G. Experience relevance and strongest evidence","Heading2")
    for item in result['strongest']:
        p(f"<b>{escape(item['category'])} — {escape(item['level'])}</b>")
        for ev in item['evidence_details'][:2]: p("• "+escape(ev['source'])+" · "+escape(ev['section'])+" (source confidence: "+escape(ev['source_confidence'])+"): "+escape(ev['text']))
    p("H. CV improvement recommendations","Heading2"); p("Where accurate, quantify outcomes and timeframe; describe personal actions and project scope; name relevant tools and methods; distinguish coursework from applied project work.")
    p("I. ATS formatting and readability","Heading2"); p(f"File: {escape(cv['filename'])}; {cv.get('word_count',0)} words; {len(warnings)} parsing warnings. Review extracted text and original file for reading order, scanned pages, contact details and hidden text flags.")
    p("J. Recruiter-style assessment","Heading2"); p(escape(result['note']))
    doc.build(story); return buf.getvalue()
