# run.py
import os
import json
import traceback
from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz
import asyncio
from dotenv import load_dotenv

load_dotenv()

# optional redis (async). If REDIS_URL is empty, disable caching.
REDIS_URL = os.getenv("REDIS_URL", "") or None
redis_client = None
if REDIS_URL:
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None

# Gemini setup (google generative ai)
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or None
if GEMINI_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        GENAI_AVAILABLE = True
    except Exception:
        GENAI_AVAILABLE = False
else:
    GENAI_AVAILABLE = False

app = FastAPI(title="Ilaaj — AI Health Companion")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# dataset path
DATA_PATH = os.path.join("database", "disease_dataset.json")
if not os.path.exists(DATA_PATH):
    raise FileNotFoundError(f"Dataset not found at {DATA_PATH}. Place disease_dataset.json in /database")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DISEASE_DB = json.load(f)

# normalize helper
def normalize_text(s: str) -> str:
    return s.strip().lower()

def score_match(user_symptoms: List[str], known_symptoms: List[str]) -> float:
    """
    For each user symptom, find the best fuzzy match among known symptoms using token_set_ratio.
    Average those best scores to get a 0..100 raw similarity.
    We'll then scale that raw similarity into a realistic confidence percentage.
    """
    if not user_symptoms or not known_symptoms:
        return 0.0
    total = 0.0
    for us in user_symptoms:
        best = 0.0
        for ks in known_symptoms:
            r = fuzz.token_set_ratio(us, ks)  # 0..100
            if r > best:
                best = r
        total += best
    raw = total / len(user_symptoms)  # 0..100

    # scaling to produce realistic-looking percentages:
    # - Raw near 100 becomes ~95%
    # - Raw near 0 becomes ~10%
    # - Non-linear curve to emphasize high matches
    if raw <= 10:
        conf = raw * 0.8  # 0..8
    else:
        # map [10..100] -> [20..95] roughly
        conf = 20 + (raw - 10) * (75 / 90)
    # clamp
    conf = max(0.0, min(conf, 95.0))
    return round(conf, 2)


async def top_matches_from_db(symptoms_text: str, top_n: int = 10):
    parts = [normalize_text(p) for p in symptoms_text.split(",") if p.strip()]
    if not parts:
        return []
    results = []
    for entry in DISEASE_DB:
        disease_name = entry.get("Disease") or entry.get("disease") or ""
        known = entry.get("Symptom") or entry.get("symptom") or entry.get("Symptoms") or entry.get("symptoms") or []
        known = [normalize_text(str(s)) for s in known if str(s).strip()]
        if not known:
            continue
        score = score_match(parts, known)  # 0..95
        if score > 0:
            results.append({"disease": disease_name, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    # ensure results appear realistic (first one tends to be highest)
    return results[:top_n]

# -------------------- Pages --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})

@app.get("/remedies", response_class=HTMLResponse)
async def remedies_page(request: Request):
    # page will fetch remedies via JS from /api/remedies
    return templates.TemplateResponse("remedies.html", {"request": request})

@app.get("/result", response_class=HTMLResponse)
async def result_page(request: Request):
    return templates.TemplateResponse("result.html", {"request": request})

# -------------------- API --------------------
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    symptoms = data.get("symptoms", "")
    if not isinstance(symptoms, str) or not symptoms.strip():
        return JSONResponse({"results": [], "source": "db"})
    cache_key = f"diagnose:{symptoms.strip().lower()}"
    # try cache
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return JSONResponse({"results": json.loads(cached), "source": "cache"})
        except Exception:
            pass
    results = await top_matches_from_db(symptoms, top_n=10)
    source = "db"
    # If DB yields no or very low confidence, leave DB results — we do NOT call Gemini for diagnosis here.
    # Trim to top 10
    results = results[:10]
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(results), ex=60 * 60)
        except Exception:
            pass
    return JSONResponse({"results": results, "source": source})

async def call_gemini_for_remedies(disease_name: str):
    """
    Call Gemini to return a JSON array of short remedies. Prompts ensure we get JSON array.
    """
    if not GENAI_AVAILABLE:
        return None, "gemini_unavailable"

    try:
        import google.generativeai as genai  # local import
        model = genai.GenerativeModel("gemini-1.5-pro")
        prompt = (
            f"Provide 4 concise, safe, non-prescriptive home remedies or self-care suggestions "
            f"for the disease named '{disease_name}'. Return only a JSON array of strings. Example:\n"
            r'["Rest and hydrate.", "Use saline nasal spray.", ...]'
        )
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or str(resp)
        # Try to locate JSON array in the returned text
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            # attempt to extract substring between first [ and last ]
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(text[start:end])
                except Exception:
                    parsed = None
        if isinstance(parsed, list):
            # ensure strings
            parsed = [str(x).strip() for x in parsed if str(x).strip()]
            return parsed, "gemini"
        # fallback: try splitting lines
        lines = [l.strip("•- \t") for l in text.splitlines() if l.strip()]
        if lines:
            return lines[:6], "gemini_text"
        return None, "gemini_empty"
    except Exception:
        traceback.print_exc()
        return None, "gemini_error"

@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Accepts JSON: {"disease":"Name"} or {"diseases":["A","B"]}
    Returns: {"remedies":[{"disease":..,"remedies":[..],"source":"gemini"|"none"}]}
    We use Gemini ONLY for remedies.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    diseases = []
    if "diseases" in data and isinstance(data["diseases"], list):
        diseases = data["diseases"]
    elif "disease" in data and isinstance(data["disease"], str):
        diseases = [data["disease"]]
    else:
        return JSONResponse({"remedies": []})
    out = []
    for d in diseases:
        dn = str(d).strip()
        if not dn:
            out.append({"disease": d, "remedies": [], "source": "none"})
            continue
        cache_key = f"remedy:{dn.lower()}"
        if redis_client:
            try:
                c = await redis_client.get(cache_key)
                if c:
                    out.append(json.loads(c))
                    continue
            except Exception:
                pass
        # use Gemini only
        parsed, src = await call_gemini_for_remedies(dn)
        if parsed:
            res_obj = {"disease": dn, "remedies": parsed, "source": src}
            out.append(res_obj)
            if redis_client:
                try:
                    await redis_client.set(cache_key, json.dumps(res_obj), ex=60 * 60)
                except Exception:
                    pass
            continue
        else:
            # no remedies found
            res_obj = {"disease": dn, "remedies": [], "source": src}
            out.append(res_obj)
    return JSONResponse({"remedies": out})

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
