# main.py
import os
import json
import traceback
from urllib.parse import unquote

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# fuzzy matching
from rapidfuzz import fuzz

# optional redis
try:
    import redis
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

# optional Gemini SDK
try:
    import google.generativeai as genai
    GEMINI_SDK_AVAILABLE = True
except Exception:
    GEMINI_SDK_AVAILABLE = False

app = FastAPI(title="Ilaaj — Smart AI Health Assistant (v1)")

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "database", "disease_dataset.json")

# static + templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ---------- Config & optional services ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash", "chat-bison-001"
]
active_gemini_model = None

if GEMINI_API_KEY and GEMINI_SDK_AVAILABLE:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ Gemini SDK configured.")
    except Exception as e:
        print("⚠️ Gemini configure error:", e)
else:
    if GEMINI_API_KEY and not GEMINI_SDK_AVAILABLE:
        print("⚠️ GEMINI_API_KEY present but google-generativeai not installed.")
    else:
        print("⚠️ GEMINI_API_KEY not provided; Gemini fallback disabled.")

REDIS_URL = os.environ.get("REDIS_URL")
redis_client = None
if REDIS_URL and REDIS_AVAILABLE:
    try:
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        print("✅ Connected to Redis")
    except Exception as e:
        print("⚠️ Redis disabled (connection failed):", e)
        redis_client = None
else:
    if REDIS_URL and not REDIS_AVAILABLE:
        print("⚠️ REDIS_URL set but redis package not installed.")
    else:
        print("⚠️ REDIS_URL not provided; Redis disabled.")

# ---------- Load dataset (required) ----------
if os.path.exists(DB_PATH):
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            DISEASE_DB = json.load(f)
            print(f"✅ Loaded {len(DISEASE_DB)} diseases from {DB_PATH}")
    except Exception as e:
        print("❌ Failed to load dataset:", e)
        DISEASE_DB = []
else:
    print("❌ dataset not found at database/disease_dataset.json — please add it.")
    DISEASE_DB = []

# ---------- Utilities ----------
def normalize(s: str) -> str:
    return s.strip().lower()

def score_against_disease(user_symptoms, disease_symptoms):
    """Return 0..100 score"""
    if not disease_symptoms:
        return 0.0
    scores = []
    for us in user_symptoms:
        best = 0
        for ds in disease_symptoms:
            ds_norm = normalize(ds)
            s1 = fuzz.partial_ratio(us, ds_norm)
            s2 = fuzz.token_sort_ratio(us, ds_norm)
            best = max(best, s1, s2)
        scores.append(best)
    return float(sum(scores) / len(scores))

def top_matches_from_db(user_input_list, top_n=10):
    results = []
    for entry in DISEASE_DB:
        disease_name = entry.get("disease") or entry.get("Disease") or "Unknown"
        disease_symptoms = entry.get("symptoms") or entry.get("Symptom") or []
        score = score_against_disease(user_input_list, disease_symptoms)
        results.append({"disease": disease_name, "score": round(score, 2), "remedies": entry.get("remedies", [])})
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)
    return results_sorted[:top_n]

# ---------- Gemini helpers ----------
def _try_gemini_generate(prompt: str, candidates=None):
    """
    Try available Gemini models in order. Return text or raise.
    """
    global active_gemini_model
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        raise RuntimeError("Gemini not configured or SDK missing")
    candidates = candidates or GEMINI_MODEL_CANDIDATES
    last_exc = None
    for m in candidates:
        try:
            model = genai.GenerativeModel(m)
            resp = model.generate_content(prompt)
            text = getattr(resp, "text", None) or str(resp)
            active_gemini_model = m
            print(f"✅ Gemini model {m} worked.")
            return text
        except Exception as e:
            last_exc = e
            print(f"⚠️ Gemini model {m} failed:", e)
            continue
    raise last_exc if last_exc else RuntimeError("No Gemini model succeeded")

def gemini_diagnose(symptoms_text: str, top_n=10):
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        return []
    prompt = (
        f"You are a clinical decision support assistant. Given symptoms: \"{symptoms_text}\", "
        f"return a JSON array of up to {top_n} likely diseases with a confidence percentage 0-100, "
        "formatted EXACTLY as: [{\"disease\":\"Name\",\"score\":87.5}, ...]. No extra explanatory text."
    )
    try:
        raw = _try_gemini_generate(prompt)
        import re
        m = re.search(r"(\[\s*\{.*\}\s*\])", raw, re.S)
        json_text = m.group(1) if m else raw
        parsed = json.loads(json_text)
        results = []
        for it in parsed:
            name = it.get("disease") or it.get("Disease") or str(it)
            score = float(it.get("score") or it.get("score") or 0)
            results.append({"disease": name, "score": round(score, 2), "remedies": []})
        return results[:top_n]
    except Exception as e:
        print("⚠️ Gemini diagnose failed:", e)
        return []

def gemini_remedies(disease_name: str):
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        return None
    prompt = (
        f"You are a professional medical assistant. Provide 4 concise, non-prescriptive remedies or self-care tips "
        f"for the disease: \"{disease_name}\". Return plain text bullet points or short paragraphs."
    )
    try:
        raw = _try_gemini_generate(prompt)
        return raw.strip()
    except Exception as e:
        print("⚠️ Gemini remedies failed:", e)
        return None

# ---------- Routes / Pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/diagnose", response_class=HTMLResponse)
def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})

@app.get("/remedies", response_class=HTMLResponse)
def remedies_page(request: Request):
    return templates.TemplateResponse("remedies.html", {"request": request})

# ---------- API Endpoints ----------
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Accepts JSON: { "symptoms": "cough, fever" } or { "symptoms": ["cough","fever"] }
    Returns: {"source":"db"|"gemini"|"cache", "results":[{"disease":..,"score":..,"remedies":...},...] }
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    raw = payload.get("symptoms", "")
    # normalize to list
    if isinstance(raw, list):
        parts = [normalize(s) for s in raw if s]
    else:
        parts = [normalize(p) for p in str(raw).split(",") if p.strip()]
    if not parts:
        return JSONResponse({"error": "No symptoms provided"}, status_code=400)
    symptoms_text = ", ".join(parts)
    cache_key = f"diagnose:{symptoms_text}"
    # cache
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return JSONResponse({"source": "cache", "results": json.loads(cached.decode("utf-8"))})
        except Exception:
            pass
    # DB matches
    db_matches = top_matches_from_db(parts, top_n=20)
    top_db_score = db_matches[0]["score"] if db_matches else 0.0
    results = []
    source = "db"
    if top_db_score >= 40:
        results = db_matches[:10]
        source = "db"
    else:
        # fallback to Gemini
        gem = gemini_diagnose(symptoms_text, top_n=10)
        if gem:
            results = gem
            source = "gemini"
        else:
            results = db_matches[:10]
            source = "db"
    # enrich remedies from DB where available
    for r in results:
        if not r.get("remedies"):
            # try find in DB entry
            for entry in DISEASE_DB:
                if normalize(entry.get("disease","")) == normalize(r.get("disease","")):
                    r["remedies"] = entry.get("remedies", [])
                    break
    # cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(results))
        except Exception:
            pass
    return JSONResponse({"source": source, "results": results})

@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Input:
      { "diseases": ["Name1","Name2", ...] }
    Or:
      { "disease": "Name" }
    Returns:
      {"remedies":[{"disease":..,"remedies": "... or []"}]}
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error":"Invalid JSON"}, status_code=400)
    diseases = []
    if "diseases" in payload and isinstance(payload["diseases"], list):
        diseases = [str(x) for x in payload["diseases"] if x]
    elif "disease" in payload:
        diseases = [payload["disease"]]
    else:
        return JSONResponse({"error":"No disease(s) provided"}, status_code=400)
    result_list = []
    for d in diseases:
        found = None
        for entry in DISEASE_DB:
            if normalize(entry.get("disease","")) == normalize(d):
                found = entry.get("remedies", [])
                break
        if found:
            result_list.append({"disease": d, "remedies": found, "source": "db"})
        else:
            # try cache
            cache_key = f"remedy:{normalize(d)}"
            cached = None
            if redis_client:
                try:
                    c = redis_client.get(cache_key)
                    if c:
                        cached = c.decode("utf-8")
                except Exception:
                    cached = None
            if cached:
                result_list.append({"disease": d, "remedies": cached, "source": "cache"})
            else:
                # Gemini fallback
                gem = gemini_remedies(d)
                if gem:
                    result_list.append({"disease": d, "remedies": gem, "source": "gemini"})
                    if redis_client:
                        try:
                            redis_client.setex(cache_key, 86400, gem)
                        except Exception:
                            pass
                else:
                    result_list.append({"disease": d, "remedies": "No remedies available", "source": "none"})
    return JSONResponse({"remedies": result_list})

# simple health check
@app.get("/health")
def health():
    return JSONResponse({"status":"ok"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
