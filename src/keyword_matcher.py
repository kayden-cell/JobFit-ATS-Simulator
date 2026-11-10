import re
DIRECT = re.compile(r"\b(led|delivered|implemented|achieved|reduced|saved|optimized|optimised|analyzed|analysed|designed|coordinated|managed|developed|performed|conducted|piloted|built|created|negotiated|supported|participated|contributed|worked on|responsible for|internship|stage|projet|réalisé|réduction|analysé|optimisé|coordonné|géré)\b", re.I)
THEORY = re.compile(r"\b(course|coursework|academic|theory|theoretical|certification|trained|training|familiar with|knowledge of|notions|formation|cours)\b", re.I)

def classify(text: str, terms: list[str], segments: list[dict] | None = None) -> dict:
    details=[]; seen=set()
    source_segments=segments or [{"source":"Extracted text","section":"Unknown section","text":text}]
    for segment in source_segments:
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+",segment.get("text", "")):
            sentence=sentence.strip()
            matched=[term for term in terms if re.search(r"(?i)\b"+re.escape(term)+r"\b",sentence)]
            key=(segment.get("source"),sentence)
            if matched and sentence and key not in seen:
                seen.add(key)
                source=segment.get("source","Source not identified")
                section=segment.get("section","Section not identified")
                details.append({"text":sentence[:500],"source":source,"section":section,"source_confidence":"High" if source.startswith(("Page ","Paragraph ","Table ")) else "Low","section_confidence":"High" if section!="Section not detected" else "Not detected","matched_terms":matched})
    details=details[:6]
    evidence=[item["text"] for item in details]
    level="Missing competency" if not details else "Direct experience" if any(DIRECT.search(s) for s in evidence) else "Theoretical knowledge" if any(THEORY.search(s) for s in evidence) else "Partial practical experience"
    return {"level":level,"evidence":evidence,"evidence_details":details}

def match_categories(text: str, categories: dict, segments: list[dict] | None = None) -> dict:
    return {n:{"weight":v["weight"],**classify(text,v["terms"],segments)} for n,v in categories.items()}

def keyword_coverage(text: str, terms: list[str]) -> dict:
    import re
    present=[t for t in terms if re.search(r"(?i)\b"+re.escape(t)+r"\b",text)]
    return {"present":present,"missing":[t for t in terms if t not in present],"ratio":len(present)/len(terms) if terms else 0.0}
