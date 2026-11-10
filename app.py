import os
import hashlib
import io
import subprocess
import sys
from pathlib import Path
from html import escape

try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    _running_in_streamlit = get_script_run_ctx(suppress_warning=True) is not None
except Exception:
    _running_in_streamlit = False

if not _running_in_streamlit and os.environ.get("ATS_SIMULATOR_LAUNCHED") != "1":
    _env = os.environ.copy()
    _env["ATS_SIMULATOR_LAUNCHED"] = "1"
    try:
        raise SystemExit(subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())],
            cwd=str(Path(__file__).resolve().parent), env=_env
        ))
    except KeyboardInterrupt:
        raise SystemExit(0)

import streamlit as st
import pandas as pd
from docx import Document
from src.resume_parser import parse_resume
from src.job_parser import parse_job
from src.semantic_matcher import semantic_similarity
from src.scoring_engine import evaluate
from src.report_generator import make_report
from src.job_url_importer import extract_job_url

def _docx_preview_html(data: bytes) -> str:
    doc=Document(io.BytesIO(data))
    blocks=[]
    for paragraph in doc.paragraphs:
        text=escape(paragraph.text)
        if not text.strip(): continue
        style=(paragraph.style.name or "").casefold()
        if style.startswith("heading") or style=="title": blocks.append(f"<h3>{text}</h3>")
        else: blocks.append(f"<p>{text}</p>")
    for table in doc.tables:
        rows=[]
        for row in table.rows:
            cells="".join(f"<td>{escape(cell.text).replace(chr(10),'<br>')}</td>" for cell in row.cells)
            rows.append(f"<tr>{cells}</tr>")
        blocks.append("<table>"+"".join(rows)+"</table>")
    return "<html><head><style>body{font-family:Arial,sans-serif;padding:24px;line-height:1.5;color:#202124;background:#fff}h3{margin:18px 0 6px}p{margin:4px 0 10px}table{border-collapse:collapse;margin:12px 0;width:100%}td{border:1px solid #bbb;padding:6px;vertical-align:top}</style></head><body>"+"".join(blocks)+"</body></html>"

st.set_page_config(page_title="JobFit ATS Simulator",page_icon="📋",layout="wide")
if "reset_version" not in st.session_state: st.session_state["reset_version"]=0

def _reset_all_inputs():
    st.session_state["reset_version"]+=1
    for key in ("analysis","job_url_status","url_group_seed","url_group_editor_key"):
        st.session_state.pop(key,None)

reset_version=st.session_state["reset_version"]
header_col,reset_col=st.columns([5,1])
header_col.title("JobFit ATS Simulator")
reset_col.button("Reset all inputs",on_click=_reset_all_inputs,help="Clear the job description, requirements, competency table, uploaded files and analysis results.")
st.caption("Independent simulation.")
with st.sidebar:
    st.header("Job description")
    with st.form(f"job_url_import_form_{reset_version}"):
        job_url=st.text_input("Or enter a public job posting URL",placeholder="https://company.example/careers/job-title",key=f"job_url_{reset_version}")
        import_url=st.form_submit_button("Extract job details from URL",key=f"extract_job_url_{reset_version}")
    if import_url:
        if not job_url.strip():
            st.session_state["job_url_status"]=("error","Enter a job posting URL first.")
        else:
            try:
                imported=extract_job_url(job_url)
                st.session_state[f"custom_job_text_{reset_version}"]=imported["job_text"]
                st.session_state[f"qualification_education_{reset_version}"]=imported["qualifications"]["Education"]
                st.session_state[f"qualification_experience_{reset_version}"]=imported["qualifications"]["Experience"]
                st.session_state[f"qualification_technical_{reset_version}"]=imported["qualifications"]["Technical competencies"]
                st.session_state[f"qualification_software_{reset_version}"]=imported["qualifications"]["Software"]
                st.session_state[f"qualification_soft_skills_{reset_version}"]=imported["qualifications"]["Soft skills"]
                st.session_state["url_group_seed"]=pd.DataFrame(imported["groups"],columns=["Category","Weight (%)","Keywords"])
                st.session_state["url_group_editor_key"]=f"competency_editor_url_{reset_version}_"+hashlib.sha256(imported["url"].encode()).hexdigest()[:16]
                st.session_state["job_url_status"]=("success",f"Imported {imported['title']}. Review the extracted fields and competency draft before analysis. Structured job data: {'found' if imported['structured_data'] else 'not found; page-text extraction used' }. Weights are blank by design. If a competency CSV is also selected, that CSV takes precedence over the URL draft.")
            except ModuleNotFoundError as exc:
                package="requests" if exc.name=="requests" else exc.name
                st.session_state["job_url_status"]=("error",f"Missing package ‘{package}’. In the VS Code terminal for this project, run: python -m pip install -r requirements.txt, then restart the app.")
            except Exception as exc:
                st.session_state["job_url_status"]=("error",f"Could not extract that job page: {exc}")
    if "job_url_status" in st.session_state:
        level,message=st.session_state["job_url_status"]
        getattr(st,level)(message)
    job_text=st.text_area("Paste or edit target job description",value="",height=360,key=f"custom_job_text_{reset_version}",placeholder="Paste the full job description here…")
    job_file=st.file_uploader("Or upload a plain-text job description",type=["txt"],key=f"job_{reset_version}")
    if job_file and not job_text.strip(): job_text=job_file.getvalue().decode("utf-8",errors="replace")
    st.markdown("**Candidate qualification requirements for this job**")
    st.caption("Enter each area from this job posting. If absent, enter ‘Not specified’. These fields feed semantic comparison and the report; add their keywords to the weighted competency table/CSV too.")
    qualification_inputs={
        "Education":st.text_area("Education",key=f"qualification_education_{reset_version}",height=80,placeholder="Required degrees, disciplines, licenses…"),
        "Experience":st.text_area("Experience",key=f"qualification_experience_{reset_version}",height=80,placeholder="Years, industries, role or project experience…"),
        "Technical competencies":st.text_area("Technical competencies",key=f"qualification_technical_{reset_version}",height=100,placeholder="Methods, domain knowledge, technical skills…"),
        "Software":st.text_area("Software",key=f"qualification_software_{reset_version}",height=80,placeholder="Required software, tools, platforms…"),
        "Soft skills":st.text_area("Soft skills",key=f"qualification_soft_skills_{reset_version}",height=80,placeholder="Communication, autonomy, collaboration…"),
    }
    st.markdown("**Competency groups for this role**")
    st.caption("Upload a CSV or add rows directly. Use one row per competency group; weights should total 100%.")
    st.download_button("Download blank CSV template",data="Category,Weight (%),Keywords\n",file_name="competency_groups_template.csv",mime="text/csv")
    groups_file=st.file_uploader("Upload competency groups CSV",type=["csv"],key=f"competency_csv_{reset_version}")
    csv_error=None
    imported_table=pd.DataFrame(columns=["Category","Weight (%)","Keywords"])
    if groups_file:
        try:
            raw=groups_file.getvalue()
            incoming=pd.read_csv(io.BytesIO(raw))
            col_map={str(c).strip().casefold():c for c in incoming.columns}
            aliases={"category":["category","competency","competency group"],"weight":["weight (%)","weight","weight percent"],"keywords":["keywords","key words"]}
            selected={target:next((col_map[a] for a in names if a in col_map),None) for target,names in aliases.items()}
            missing=[name for name,col in selected.items() if col is None]
            if missing:
                csv_error="CSV needs columns for Category, Weight (%) and Keywords. Download the template above for the expected format."
            else:
                imported_table=incoming[[selected["category"],selected["weight"],selected["keywords"]]].copy()
                imported_table.columns=["Category","Weight (%)","Keywords"]
                imported_table=imported_table.dropna(how="all")
                imported_table["Category"]=imported_table["Category"].fillna("").astype(str).str.strip()
                imported_table["Keywords"]=imported_table["Keywords"].fillna("").astype(str).str.strip()
                imported_table["Weight (%)"]=pd.to_numeric(imported_table["Weight (%)"],errors="coerce")
                if imported_table.empty: csv_error="The uploaded CSV has no competency rows yet. Add at least one row."
                elif imported_table[["Category","Weight (%)","Keywords"]].isna().any().any() or (imported_table["Category"]=="").any() or (imported_table["Keywords"]=="").any():
                    csv_error="Every CSV row needs a category name, numeric weight and at least one keyword."
                elif ((imported_table["Weight (%)"]<0)|(imported_table["Weight (%)"]>100)).any():
                    csv_error="Weights must be between 0 and 100."
        except Exception as exc:
            csv_error=f"Could not read CSV: {exc}"
    if csv_error: st.error(csv_error)
    if groups_file:
        editor_key=f"competency_editor_{reset_version}_"+hashlib.sha256(groups_file.getvalue()).hexdigest()[:16]
        table_data=imported_table
    elif "url_group_seed" in st.session_state:
        editor_key=st.session_state["url_group_editor_key"]
        table_data=st.session_state["url_group_seed"]
    else:
        editor_key=f"competency_editor_empty_{reset_version}"
        table_data=pd.DataFrame(columns=["Category","Weight (%)","Keywords"])
    if not csv_error:
        keyword_table=st.data_editor(table_data,num_rows="dynamic",width="stretch",hide_index=True,key=editor_key,column_config={"Category":st.column_config.TextColumn(required=False),"Weight (%)":st.column_config.NumberColumn(min_value=0,max_value=100,step=1,format="%d",required=False),"Keywords":st.column_config.TextColumn(help="Comma-separated phrases; quote the CSV cell if it contains commas")})
    else:
        keyword_table=pd.DataFrame(columns=["Category","Weight (%)","Keywords"])
upload=st.file_uploader("Upload candidate CV",type=["pdf","docx"],key=f"candidate_cv_{reset_version}")
if upload:
    ocr_requested=False
    if upload.name.casefold().endswith(".pdf"):
        ocr_requested=st.checkbox("Try OCR on scanned PDF pages",key=f"enable_ocr_{reset_version}",help="Requires Tesseract OCR installed on this computer with French (fra) and English (eng) language data.")
    try:
        cv=parse_resume(upload.name,upload.getvalue(),enable_ocr=ocr_requested); left,right=st.columns([1,1])
        with left:
            st.subheader("Candidate profile")
            st.markdown(f"### {escape(cv['name_suggestion']) if cv['name_suggestion'] else 'Name not confidently detected'}")
            contact_left,contact_right=st.columns(2)
            with contact_left:
                st.caption("EMAIL")
                if cv["emails"]:
                    for email in cv["emails"]: st.markdown(f"[{escape(email)}](mailto:{escape(email)})")
                else: st.write("Not detected")
            with contact_right:
                st.caption("PHONE")
                st.write("\n".join(cv["phones"]) if cv["phones"] else "Not detected")
            metric_left,metric_right=st.columns(2)
            metric_left.metric("Text extracted",f"{cv['word_count']:,} words")
            page_count=cv["metadata"].get("pages")
            metric_right.metric("Pages",str(page_count) if page_count is not None else "DOCX")
            st.markdown("**Skills detected**")
            if cv["skills"]:
                chips="".join(f'<span style="display:inline-block;background:#243247;color:#e6edf7;border:1px solid #42536a;border-radius:14px;padding:4px 10px;margin:3px;font-size:0.85rem">{escape(skill)}</span>' for skill in cv["skills"])
                st.markdown(chips,unsafe_allow_html=True)
            else: st.caption("No skills from the parser’s built-in skill list were detected.")
            st.markdown("**Languages detected**")
            if cv["language_details"]: st.text(cv["language_details"])
            else: st.write(", ".join(cv["languages"]) if cv["languages"] else "Not detected")
            for label,key in [("Education","education"),("Professional experience","experience"),("Certifications","certifications")]:
                with st.expander(label):
                    if cv[key]: st.text(cv[key])
                    else: st.caption(f"No {label.lower()} section was detected in the extracted text.")
            with st.expander("Software and tools"):
                if cv["software"]: st.text(cv["software"])
                else: st.caption("No software or tools section detected. Skill terms from the full CV are shown above when recognized.")
            with st.expander("Soft skills"):
                if cv["soft_skills"]: st.text(cv["soft_skills"])
                else: st.caption("No soft-skills section detected.")
            with st.expander("Dates and years detected"):
                st.write(", ".join(cv["dates"]) if cv["dates"] else "No dates detected")
            for warning in cv["warnings"]: st.warning(warning)
            with st.expander("View uploaded CV"):
                st.download_button("Download original CV",data=upload.getvalue(),file_name=upload.name,mime=upload.type or "application/octet-stream",key=f"download_original_cv_{reset_version}")
                if upload.name.casefold().endswith(".pdf"):
                    if len(upload.getvalue())>15_000_000:
                        st.info("This PDF is over 15 MB, so inline preview is disabled. Download the original CV to view it.")
                    else:
                        import fitz
                        pdf_doc=fitz.open(stream=upload.getvalue(),filetype="pdf")
                        page_key="cv_pdf_page_"+hashlib.sha256(upload.getvalue()).hexdigest()[:12]
                        page_number=st.selectbox("PDF page",options=list(range(1,len(pdf_doc)+1)),format_func=lambda n:f"Page {n} of {len(pdf_doc)}",key=page_key)
                        page=pdf_doc[page_number-1]
                        scale=min(1.5,1800/max(page.rect.width,page.rect.height))
                        pixmap=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
                        st.image(pixmap.tobytes("png"),caption=f"Page {page_number}",width="stretch")
                else:
                    st.caption("DOCX content preview. This shows document text and tables; it may not exactly reproduce Word page layout.")
                    st.components.v1.html(_docx_preview_html(upload.getvalue()),height=800,scrolling=True)
            with st.expander("Review extracted text"): st.text(cv["text"])
        with right:
            custom_categories={}
            for _,row in keyword_table.iterrows():
                name=str(row.get("Category","")).strip()
                terms=[x.strip() for x in str(row.get("Keywords","")).split(",") if x.strip() and x.strip().lower()!="nan"]
                try: weight=float(row.get("Weight (%)",0))
                except (TypeError,ValueError): weight=0
                if name and terms and weight>=0: custom_categories[name]={"weight":weight,"terms":terms}
            if st.button("Run compatibility analysis",type="primary"):
                if not job_text.strip(): st.error("Provide a job description first.")
                elif any(not value.strip() for value in qualification_inputs.values()): st.error("Complete all five qualification areas, or enter ‘Not specified’ for areas the job posting does not mention.")
                elif not cv["text"]: st.error("No readable text extracted. Scanned-PDF OCR is not built in.")
                else:
                    total=sum(x["weight"] for x in custom_categories.values())
                    if not custom_categories: st.error("Add at least one competency group with keywords.")
                    elif abs(total-100)>0.01: st.error(f"Competency weights currently total {total:g}%. Adjust them to total 100% before analysis.")
                    else:
                        analysis_job_text=job_text+"\n\nCandidate qualification requirements:\n"+"\n".join(f"{name}: {value}" for name,value in qualification_inputs.items())
                        job=parse_job(analysis_job_text,custom_categories,qualification_inputs)
                        with st.spinner("Comparing evidence with requirements…"):
                            result=evaluate(cv,job,semantic_similarity(cv["text"],analysis_job_text))
                        st.session_state["analysis"]=(cv,result,job_text,custom_categories,qualification_inputs.copy())
            if ("analysis" in st.session_state and len(st.session_state["analysis"])>4 and st.session_state["analysis"][0]["filename"]==cv["filename"]
                    and st.session_state["analysis"][2]==job_text and st.session_state["analysis"][3]==custom_categories and st.session_state["analysis"][4]==qualification_inputs):
                cv,result,_,_,_=st.session_state["analysis"]
                st.metric("Overall compatibility",f"{result['score']}/100",result["band"]); st.progress(result["score"]/100)
                exp=result["experience_relevance"]; edu=result["education_compatibility"]
                st.write(f"Technical: {result['technical_score']}/100 · Experience: {str(exp)+'/100' if exp is not None else 'not configured'} · Education: {str(edu)+'/100' if edu is not None else 'not configured'}")
                st.caption(f"Semantic comparison: {result['semantic']['method']} ({result['semantic']['score']:.0%})")
                st.subheader("Competency evidence")
                st.caption("Source confidence describes where extracted text was located (page or paragraph), not whether the candidate’s claim is independently verified. Check every excerpt against the original CV.")
                st.dataframe([{"Category":k,"Weight":f"{v['weight']}%","Classification":v['level'],"Evidence":"\n".join(f"[{e['source']} · {e['section']} · source confidence: {e['source_confidence']}] {e['text']} (matched: {', '.join(e['matched_terms'])})" for e in v['evidence_details']) or "No supporting excerpt found in extracted text."} for k,v in result['matches'].items()],width="stretch",hide_index=True)
                st.subheader("Keyword coverage")
                st.write(f"{result['keyword_coverage']['ratio']:.0%}: {', '.join(result['keyword_coverage']['present']) or 'No target terms detected'}")
                st.write("**Missing categories:** "+(", ".join(result['missing']) or "None flagged")); st.write("**Weakly supported:** "+(", ".join(result['weak']) or "None flagged"))
                st.subheader("Strongest matching evidence")
                for item in result['strongest']:
                    st.markdown(f"**{item['category']}** — {item['level']}")
                    for ev in item['evidence_details']:
                        st.write(f"• [{ev['source']} · {ev['section']} · source confidence: {ev['source_confidence']}] {ev['text']} — matched: {', '.join(ev['matched_terms'])}")
                st.info(result["note"])
                st.download_button("Download evaluation report (PDF)",make_report(cv,result),file_name="candidate_evaluation_report.pdf",mime="application/pdf")
    except Exception as exc: st.error(f"Could not parse this file: {exc}")
else: st.info("Upload a PDF or DOCX CV to review extracted details and run the analysis.")
st.divider(); st.caption("Indicative ranges: 90–100 Very strong · 75–89 Strong · 60–74 Moderate · 40–59 Weak · below 40 Low. Score must not automatically reject a candidate.")
