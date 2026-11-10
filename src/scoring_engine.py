from .keyword_matcher import match_categories,keyword_coverage
LEVEL={"Direct experience":1.0,"Partial practical experience":0.65,"Theoretical knowledge":0.30,"Missing competency":0.0}

def evaluate(cv: dict,job: dict,semantic: dict) -> dict:
    matches=match_categories(cv.get("text",""),job["categories"],cv.get("evidence_segments"))
    weighted=sum(v["weight"]*LEVEL[v["level"]] for v in matches.values())
    score=round(min(100,weighted+10*semantic.get("score",0)),1)
    technical_items=[v for k,v in matches.items() if not any(tag in k.casefold() for tag in ("soft skill","education","experience"))]
    if not technical_items: technical_items=list(matches.values())
    technical=round(sum(v["weight"]*LEVEL[v["level"]] for v in technical_items)/max(1,sum(v["weight"] for v in technical_items))*100,1)
    allterms=list(dict.fromkeys(t for v in job["categories"].values() for t in v["terms"]))
    coverage=keyword_coverage(cv.get("text",""),allterms)
    missing=[k for k,v in matches.items() if v["level"]=="Missing competency"]
    weak=[k for k,v in matches.items() if v["level"] in ("Theoretical knowledge","Partial practical experience")]
    strongest=sorted(((k,v) for k,v in matches.items() if v["evidence"]),key=lambda kv:LEVEL[kv[1]["level"]]*kv[1]["weight"],reverse=True)
    scoreband="Very strong alignment" if score>=90 else "Strong alignment" if score>=75 else "Moderate alignment" if score>=60 else "Weak alignment" if score>=40 else "Low alignment"
    exp_items=[v for k,v in matches.items() if "experience" in k.casefold()]
    edu_items=[v for k,v in matches.items() if "education" in k.casefold()]
    experience_score=round(sum(LEVEL[v["level"]] for v in exp_items)/len(exp_items)*100,1) if exp_items else None
    education_score=round(sum(LEVEL[v["level"]] for v in edu_items)/len(edu_items)*100,1) if edu_items else None
    return {"score":score,"band":scoreband,"technical_score":technical,"experience_relevance":experience_score,"education_compatibility":education_score,"keyword_coverage":coverage,"matches":matches,"missing":missing,"weak":weak,"strongest":[{"category":k,"level":v["level"],"evidence":v["evidence"],"evidence_details":v["evidence_details"]} for k,v in strongest[:4]],"semantic":semantic,"qualifications":job.get("qualifications",{}),"note":"Indicative decision support only. Source confidence describes extraction location, not claim verification. Section labels and page/paragraph locations are parsing heuristics; verify excerpts against the original CV. Do not use this score as an automatic rejection rule."}
