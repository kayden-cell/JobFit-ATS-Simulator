import re

def parse_job(text: str, categories: dict, qualifications: dict | None = None) -> dict:
    if not categories:
        raise ValueError("Enter job-specific competency groups before analysis.")
    return {"text": text.strip(), "categories": categories, "qualifications": qualifications or {}, "sentences": [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 20]}
  