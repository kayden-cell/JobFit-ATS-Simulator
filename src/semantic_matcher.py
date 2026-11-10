def semantic_similarity(cv_text: str, job_text: str) -> dict:
    cv=[s.strip() for s in cv_text.splitlines() if len(s.strip())>30]
    job=[s.strip() for s in job_text.splitlines() if len(s.strip())>20]
    if not cv or not job: return {"score":0.0,"method":"unavailable","matches":[]}
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
        model=SentenceTransformer("all-MiniLM-L6-v2"); a=model.encode(cv,normalize_embeddings=True); b=model.encode(job,normalize_embeddings=True)
        sim=cosine_similarity(b,a); method="sentence-transformers/all-MiniLM-L6-v2"
    except Exception:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            mat=TfidfVectorizer(ngram_range=(1,2)).fit_transform(cv+job); sim=cosine_similarity(mat[len(cv):],mat[:len(cv)]); method="TF-IDF cosine similarity (fallback)"
        except Exception: return {"score":0.0,"method":"unavailable (install scikit-learn)","matches":[]}
    best=sim.max(axis=1); idx=sim.argmax(axis=1)
    matches=[{"job_text":job[i][:300],"cv_text":cv[int(idx[i])][:300],"similarity":float(best[i])} for i in range(len(job))]
    vals=sorted((m["similarity"] for m in matches),reverse=True)[:8]
    return {"score":sum(vals)/len(vals),"method":method,"matches":sorted(matches,key=lambda x:x["similarity"],reverse=True)[:8]}
