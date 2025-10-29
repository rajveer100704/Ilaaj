# run.py
import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from difflib import SequenceMatcher
from typing import List

app = FastAPI(title="Ilaaj — AI Health Companion")

# static & templates (keep paths exactly as your structure)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# dataset paths
DATASET_PATH = os.path.join("database", "disease_dataset.json")
REMEDIES_PATH = os.path.join("database", "remedies.json")  # optional

# load dataset once
if not os.path.exists(DATASET_PATH):
    raise FileNotFoundError(f"Dataset missing at {DATASET_PATH}")
with open(DATASET_PATH, "r", encoding="utf-8") as f:
    DISEASE_DB = json.load(f)

# optional remedies DB (list of {"Disease":.., "Remedies":[..]})
REMEDIES_DB = {}
if os.path.exists(REMEDIES_PATH):
    try:
        with open(REMEDIES_PATH, "r", encoding="utf-8") as f:
            rr = json.load(f)
            for e in rr:
                name = e.get("Disease", "").strip().lower()
                if name:
                    REMEDIES_DB[name] = e.get("Remedies", [])
    except Exception:
        REMEDIES_DB = {}

def seq_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def top_matches_from_db(user_symptoms_text: str, top_n: int = 10):
    # user_symptoms_text: comma separated
    parts = [p.strip().lower() for p in user_symptoms_text.split(",") if p.strip()]
    if not parts:
        return []

    results = []
    for entry in DISEASE_DB:
        disease = entry.get("Disease") or entry.get("disease") or ""
        known_symptoms = entry.get("Symptom") or entry.get("symptom") or entry.get("Symptoms") or entry.get("symptoms") or []
        known_symptoms = [str(s).strip().lower() for s in known_symptoms if str(s).strip()]
        if not known_symptoms:
            continue

        # score: average of best similarity for each user symptom against the disease's symptoms
        per_user_scores = []
        for us in parts:
            best = 0.0
            for ks in known_symptoms:
                r = seq_ratio(us, ks)
                if r > best:
                    best = r
            per_user_scores.append(best)
        # average similarity (0..1)
        avg_similarity = sum(per_user_scores) / len(per_user_scores) if per_user_scores else 0.0
        score_pct = round(avg_similarity * 100, 2)
        # only include if at least some overlap
        if score_pct > 0:
            results.append({"disease": disease, "score": score_pct})

    # sort by score desc
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

# server pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})

@app.get("/remedies", response_class=HTMLResponse)
async def remedies_page(request: Request):
    return templates.TemplateResponse("remedies.html", {"request": request})

@app.get("/result", response_class=HTMLResponse)
async def result_page(request: Request):
    return templates.TemplateResponse("result.html", {"request": request})

# API endpoints
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Expects JSON: { "symptoms": "fever, cough" }
    Returns: { "results": [ {"disease":"X","score":85.0}, ... ] , "source": "db"|"gemini" }
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    symptoms = payload.get("symptoms", "")
    if not isinstance(symptoms, str) or not symptoms.strip():
        return JSONResponse({"results": []})

    # try DB first
    results = top_matches_from_db(symptoms, top_n=10)
    source = "db"
    # fallback to Gemini if no good results
    if not results or (len(results) == 1 and results[0]["score"] < 30):
        GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        if GEMINI_KEY:
            # use google generative AI client if available
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel("gemini-1.5-pro-latest")
                prompt = (
                    f"Given the user's symptoms: '{symptoms}', "
                    "return a JSON array of the top 10 likely diseases with 'disease' and 'score' (percentage) fields. "
                    "Example: [{\"disease\":\"Influenza\",\"score\":78.5}, ...]"
                )
                resp = model.generate_content(prompt)
                # resp may contain text; try to parse JSON from it
                text = getattr(resp, "text", None) or str(resp)
                parsed = None
                try:
                    parsed = json.loads(text)
                except Exception:
                    # try to extract JSON substring
                    start = text.find("[")
                    end = text.rfind("]") + 1
                    if start != -1 and end != -1:
                        parsed = json.loads(text[start:end])
                if isinstance(parsed, list):
                    # normalize
                    parsed2 = []
                    for p in parsed[:10]:
                        if isinstance(p, dict) and "disease" in p:
                            score = float(p.get("score", 0) or 0)
                            parsed2.append({"disease": p.get("disease"), "score": round(score, 2)})
                    if parsed2:
                        results = parsed2
                        source = "gemini"
            except Exception:
                # ignore and keep db results
                pass

    return JSONResponse({"results": results, "source": source})

@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Accepts:
      { "disease": "Name" }  OR
      { "diseases": ["Name1","Name2"] }
    Returns:
      {"remedies":[{"disease":..,"remedies":[...],"source":"dataset"|"gemini"|"none"}]}
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    diseases = []
    if "diseases" in payload and isinstance(payload["diseases"], list):
        diseases = payload["diseases"]
    elif "disease" in payload and isinstance(payload["disease"], str):
        diseases = [payload["disease"]]
    else:
        return JSONResponse({"remedies": []})

    out = []
    GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    for d in diseases:
        dn = d.strip()
        dn_norm = dn.lower()
        # check local remedies db first
        if dn_norm in REMEDIES_DB:
            out.append({"disease": dn, "remedies": REMEDIES_DB[dn_norm], "source": "dataset"})
            continue

        # else attempt to find any dataset description and produce a simple suggestion
        # to avoid always calling Gemini, create a basic fallback from dataset symptoms
        # create a simple heuristic "suggested remedies" from symptoms in dataset (informational only)
        suggested = []
        for entry in DISEASE_DB:
            if entry.get("Disease", "").strip().lower() == dn_norm:
                # suggest basic lines using symptoms
                syms = entry.get("Symptom", [])
                if isinstance(syms, list) and syms:
                    suggested.append("Rest and monitor symptoms.")
                    suggested.append("Stay hydrated and maintain comfort.")
                    suggested.append("If symptoms worsen, seek medical attention.")
                break

        if suggested:
            out.append({"disease": dn, "remedies": suggested, "source": "heuristic"})
            continue

        # finally fallback to Gemini if key available
        if GEMINI_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel("gemini-1.5-pro-latest")
                prompt = (
                    f"Provide 5 safe, non-prescriptive home remedies or self-care suggestions "
                    f"for a patient who may have '{dn}'. Return a JSON array of strings."
                )
                resp = model.generate_content(prompt)
                text = getattr(resp, "text", None) or str(resp)
                parsed = None
                try:
                    parsed = json.loads(text)
                except Exception:
                    start = text.find("[")
                    end = text.rfind("]") + 1
                    if start != -1 and end != -1:
                        parsed = json.loads(text[start:end])
                if isinstance(parsed, list) and parsed:
                    out.append({"disease": dn, "remedies": parsed, "source": "gemini"})
                    continue
            except Exception:
                pass

        out.append({"disease": dn, "remedies": [], "source": "none"})

    return JSONResponse({"remedies": out})


# simple health check
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
