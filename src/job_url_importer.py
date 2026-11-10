from __future__ import annotations
import html
import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

MAX_BYTES = 5_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LocalATSJobImporter/1.0)"}

class _JobPageParser(HTMLParser):
    BLOCK={"address","article","aside","blockquote","br","dd","div","dl","dt","h1","h2","h3","h4","h5","h6","li","main","ol","p","section","tr","ul"}
    VOID={"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
    IGNORE={"footer","header","nav","noscript","script","style","svg"}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[]; self.jsonld=[]; self._script_type=""; self._json_active=False; self._skip_stack=[]; self._title=False; self.title=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs); tag=tag.casefold()
        if tag=="script":
            self._script_type=attrs.get("type","").casefold()
            self._json_active="ld+json" in self._script_type
            if self._json_active: self.jsonld.append([])
            else: self._skip_stack.append(tag)
            return
        if self._skip_stack:
            if tag not in self.VOID: self._skip_stack.append(tag)
            return
        if tag in self.IGNORE or "hidden" in attrs or attrs.get("aria-hidden","").casefold()=="true" or "display:none" in attrs.get("style","").replace(" ","").casefold():
            if tag not in self.VOID: self._skip_stack.append(tag)
            return
        if tag=="title": self._title=True
        if tag in self.BLOCK: self.parts.append("\n")
    def handle_endtag(self,tag):
        tag=tag.casefold()
        if tag=="script":
            if self._json_active: self._json_active=False
            elif self._skip_stack and self._skip_stack[-1]=="script": self._skip_stack.pop()
            return
        if self._skip_stack:
            if tag in self._skip_stack:
                index=len(self._skip_stack)-1-self._skip_stack[::-1].index(tag)
                self._skip_stack=self._skip_stack[:index]
            return
        if tag=="title": self._title=False
        if tag in self.BLOCK: self.parts.append("\n")
    def handle_data(self,data):
        if self._json_active and self.jsonld: self.jsonld[-1].append(data)
        elif not self._skip_stack:
            self.parts.append(data)
            if self._title: self.title.append(data)

def _parse_html(raw: bytes,encoding: str):
    parser=_JobPageParser()
    parser.feed(raw.decode(encoding or "utf-8",errors="replace"))
    visible="\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
    return visible,["".join(part) for part in parser.jsonld]," ".join("".join(parser.title).split())

def _validate_public_url(url: str) -> str:
    parsed=urlparse(url.strip())
    if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a complete public http(s) job posting URL.")
    host=parsed.hostname.rstrip(".").casefold()
    if host in {"localhost","localhost.localdomain"} or host.endswith((".local",".internal",".localhost")):
        raise ValueError("Local or internal addresses are not allowed.")
    try:
        addresses={ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host,None)}
    except (OSError,ValueError):
        raise ValueError("The job-site host could not be resolved.")
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Only publicly reachable job-site addresses are allowed.")
    return url

def _download(url: str) -> tuple[bytes,str,str]:
    import requests
    current=url
    for _ in range(6):
        _validate_public_url(current)
        response=requests.get(current,headers=HEADERS,timeout=(5,15),allow_redirects=False,stream=True)
        if response.is_redirect or response.is_permanent_redirect:
            location=response.headers.get("Location")
            response.close()
            if not location: raise ValueError("The job site returned a redirect without a destination.")
            current=urljoin(current,location); continue
        response.raise_for_status()
        content_type=response.headers.get("Content-Type","").casefold()
        if "html" not in content_type and "xhtml" not in content_type:
            response.close(); raise ValueError("That URL did not return an HTML job page.")
        declared=response.headers.get("Content-Length")
        if declared and int(declared)>MAX_BYTES:
            response.close(); raise ValueError("The job page is larger than the 5 MB import limit.")
        chunks=[]; size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>MAX_BYTES:
                response.close(); raise ValueError("The job page is larger than the 5 MB import limit.")
            chunks.append(chunk)
        encoding=response.encoding or "utf-8"
        response.close()
        return b"".join(chunks),current,encoding
    raise ValueError("The job page redirected too many times.")

def _plain(value) -> str:
    if value is None: return ""
    if isinstance(value,list): return "\n".join(filter(None,(_plain(x) for x in value)))
    if isinstance(value,dict):
        for key in ("name","description","value"):
            if key in value: return _plain(value[key])
        return " ".join(filter(None,(_plain(v) for v in value.values())))
    text=re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6])\s*>"," ",str(value))
    text=re.sub(r"<[^>]*>"," ",text)
    return re.sub(r"\s+"," ",html.unescape(text)).strip()

def _walk_json(value):
    if isinstance(value,dict):
        typ=value.get("@type",[])
        if isinstance(typ,str): typ=[typ]
        if any(str(t).casefold().rstrip("/").rsplit("/",1)[-1].rsplit("#",1)[-1]=="jobposting" for t in typ): yield value
        for child in value.values(): yield from _walk_json(child)
    elif isinstance(value,list):
        for child in value: yield from _walk_json(child)

def _section(text: str, headers: tuple[str,...]) -> str:
    lines=[re.sub(r"\s+"," ",line).strip(" •\t") for line in text.splitlines() if line.strip()]
    active=False; found=[]
    heading=re.compile(r"(?i)^\s*(?:"+"|".join(re.escape(h) for h in headers)+r")\s*:?\s*$")
    other=re.compile(r"(?i)^\s*(about|company|benefits|apply|how to apply|mission|responsibilities|profile|profil|missions|description|requirements|qualifications|education|experience|skills|compétences|formation|expérience|logiciels|qualifications)\s*:?\s*$")
    for line in lines:
        if heading.match(line): active=True; continue
        if other.match(line) and active: break
        if active: found.append(line)
    return "\n".join(found)

def _soft_skills(text: str) -> str:
    terms=["communication","collaboration","teamwork","team work","autonomy","autonomous","initiative","proactive","rigor","rigorous","adaptability","leadership","problem solving","analytical","organisation","organization","autonomie","communication","esprit d’équipe","rigueur","proactivité","initiative","leadership","travail en équipe"]
    lines=[line.strip(" •\t-") for line in text.splitlines() if line.strip()]
    hits=[line for line in lines if any(re.search(r"(?i)\b"+re.escape(term)+r"\b",line) for term in terms)]
    return "\n".join(dict.fromkeys(hits))

def _keywords(value: str) -> str:
    if not value or value.casefold().strip() in {"not specified","non spécifié","non spécifiée"}: return ""
    parts=[re.sub(r"^[\s•*\-–]+","",part).strip(" .") for part in re.split(r"[\n;,|]+",value)]
    parts=[part for part in parts if 2<=len(part)<=90]
    return ", ".join(dict.fromkeys(parts[:15]))

def extract_job_url(url: str) -> dict:
    raw,final_url,encoding=_download(url)
    visible,jsonld_blocks,page_title=_parse_html(raw,encoding)
    posting=None
    for script in jsonld_blocks:
        try:
            parsed=json.loads(html.unescape(script))
            posting=next(_walk_json(parsed),None)
            if posting: break
        except (json.JSONDecodeError,TypeError): continue
    title=_plain(posting.get("title")) if posting else ""
    organization=_plain(posting.get("hiringOrganization")) if posting else ""
    description=_plain(posting.get("description")) if posting else ""
    responsibilities=_plain(posting.get("responsibilities")) if posting else ""
    qualifications=_plain(posting.get("qualifications")) if posting else ""
    education=_plain(posting.get("educationRequirements")) if posting else ""
    experience=_plain(posting.get("experienceRequirements")) if posting else ""
    skills=_plain(posting.get("skills")) if posting else ""
    if not description: description=visible
    full_parts=[x for x in (title,organization,description,responsibilities,qualifications) if x]
    job_text="\n\n".join(dict.fromkeys(full_parts))
    if not job_text.strip(): raise ValueError("No readable job-posting text was found on that page.")
    education=education or _section(visible,("education","education requirements","formation","formation requise","études"))
    experience=experience or _section(visible,("experience","experience requirements","professional experience","expérience","expérience requise","expérience professionnelle"))
    technical=skills or _section(visible,("skills","technical skills","technical competencies","competencies","compétences","compétences techniques","qualifications","profil recherché"))
    software=_section(visible,("software","software skills","tools","tools and software","logiciels","outils"))
    soft=_section(visible,("soft skills","personal skills","qualities","qualities and skills","qualités","savoir-être")) or _soft_skills(visible)
    fields={"Education":education or "Not specified","Experience":experience or "Not specified","Technical competencies":technical or qualifications or "Not specified","Software":software or "Not specified","Soft skills":soft or "Not specified"}
    category_map={"Education":education,"Experience":experience,"Technical competencies":technical or qualifications,"Software":software,"Soft skills":soft}
    groups=[{"Category":name,"Weight (%)":None,"Keywords":_keywords(text)} for name,text in category_map.items() if _keywords(text)]
    title=title or page_title or "Job posting"
    return {"url":final_url,"title":title,"job_text":job_text,"qualifications":fields,"groups":groups,"structured_data":bool(posting)}
