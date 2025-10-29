# run.py
import os
import json
import traceback
from typing import List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Ilaaj — AI Health Companion")

# mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# config
DATA_PATH = os.path.join("database", "disease_dataset.json")
REMEDIES_PATH = os.path.join("database", "remedies.json")  # optional
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "") or None
PORT = int(os.getenv("PORT", "8000"))

# load dataset
if not os.path.exists(DATA_PATH):
    raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    DISEASE_DB = json.load(f)

# optional remedies DB
REMEDIES_DB = {}
if os.path.exists(REMEDIES_PATH):
    try:
        with open(REMEDIES_PATH, "r", encoding="utf-8") as f:
            arr = json.load(f)
            for e in arr:
                key = e.get("Disease", "").strip().lower()
                if key:
                    REMEDIES_DB[key] = e.get("Remedies") or []
    except Exception:
        REMEDIES_DB = {}

# async redis client
try:
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    redis_client = None


def normalize_text(s: str) -> str:
    return s.strip().lower()


def score_match(user_symptoms: List[str], known_symptoms: List[str]) -> float:
    # For each user symptom, find best fuzzy ratio among known_symptoms; average them.
    if not user_symptoms or not known_symptoms:
        return 0.0
    total = 0.0
    for us in user_symptoms:
        best = 0.0
        for ks in known_symptoms:
            # token_set_ratio deals well with order/extra words
            r = fuzz.token_set_ratio(us, ks)  # 0..100
            if r > best:
                best = r
        total += best
    avg = total / len(user_symptoms)
    # normalize to 0..1
    return avg / 100.0


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
        score = score_match(parts, known)  # 0..1
        pct = round(score * 100, 2)
        if pct > 0:
            results.append({"disease": disease_name, "score": pct})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# pages
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
    Input: {"symptoms": "fever, cough"}
    Returns: {"results":[{"disease":"X","score":87.5},...], "source":"db"|"gemini"}
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    symptoms = data.get("symptoms", "")
    if not isinstance(symptoms, str) or not symptoms.strip():
        return JSONResponse({"results": [], "source": "db"})

    cache_key = f"diagnose:{symptoms.strip().lower()}"
    # try redis
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return JSONResponse({"results": json.loads(cached), "source": "cache"})
        except Exception:
            pass

    results = await top_matches_from_db(symptoms, top_n=20)
    source = "db"
    top_score = results[0]["score"] if results else 0.0

    # fallback to Gemini if no decent DB results
    if (not results) or (top_score < 40.0 and GEMINI_KEY):
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            prompt = (
                f"User symptoms: '{symptoms}'. Provide a JSON array of up to 10 likely diseases "
                "with keys 'disease' and 'score' (percentage). Example: [{\"disease\":\"Flu\",\"score\":75.3}, ...]"
            )
            resp = model.generate_content(prompt)
            text = getattr(resp, "text", None) or str(resp)
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                # try to extract JSON array substring
                start = text.find("[")
                end = text.rfind("]") + 1
                if start != -1 and end != -1:
                    parsed = json.loads(text[start:end])
            if isinstance(parsed, list) and parsed:
                # normalize to expected format
                parsed2 = []
                for p in parsed[:10]:
                    if isinstance(p, dict) and "disease" in p:
                        try:
                            sc = float(p.get("score", 0) or 0)
                        except Exception:
                            sc = 0.0
                        parsed2.append({"disease": p.get("disease"), "score": round(sc, 2)})
                if parsed2:
                    results = parsed2
                    source = "gemini"
        except Exception:
            # if anything fails, keep DB results
            traceback.print_exc()

    # trim top 10
    results = results[:10]

    # cache
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(results), ex=60 * 60)  # 1 hour
        except Exception:
            pass

    return JSONResponse({"results": results, "source": source})


@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Accepts:
      {"disease":"Name"} or {"diseases":["A","B"]}
    Returns:
      {"remedies":[{"disease":..,"remedies":[..],"source":"dataset"|"heuristic"|"gemini"|"none"}]}
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
        dn_norm = dn.lower()
        cache_key = f"remedy:{dn_norm}"
        # check cache
        if redis_client:
            try:
                c = await redis_client.get(cache_key)
                if c:
                    out.append(json.loads(c))
                    continue
            except Exception:
                pass

        # dataset remedies
        if dn_norm in REMEDIES_DB:
            res_obj = {"disease": dn, "remedies": REMEDIES_DB[dn_norm], "source": "dataset"}
            out.append(res_obj)
            if redis_client:
                try:
                    await redis_client.set(cache_key, json.dumps(res_obj), ex=60 * 60)
                except Exception:
                    pass
            continue

        # heuristic fallback: check DISEASE_DB symptoms and produce generic suggestions
        heur = []
        for entry in DISEASE_DB:
            if entry.get("Disease", "").strip().lower() == dn_norm:
                heur = [
                    "Rest and monitor your symptoms.",
                    "Stay hydrated and maintain comfort.",
                    "Use over-the-counter pain relievers if appropriate (follow instructions).",
                    "If symptoms worsen or persist, seek medical care."
                ]
                break
        if heur:
            res_obj = {"disease": dn, "remedies": heur, "source": "heuristic"}
            out.append(res_obj)
            if redis_client:
                try:
                    await redis_client.set(cache_key, json.dumps(res_obj), ex=60 * 60)
                except Exception:
                    pass
            continue

        # gemini fallback
        if GEMINI_KEY:
            try:
                import google.generativeai as genai

                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel("gemini-1.5-pro-latest")
                prompt = (
                    f"Provide up to 6 safe, non-prescriptive home remedies or self-care suggestions for '{dn}'. "
                    "Return a JSON array of strings only."
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
                    res_obj = {"disease": dn, "remedies": parsed, "source": "gemini"}
                    out.append(res_obj)
                    if redis_client:
                        try:
                            await redis_client.set(cache_key, json.dumps(res_obj), ex=60 * 60)
                        except Exception:
                            pass
                    continue
            except Exception:
                traceback.print_exc()

        out.append({"disease": dn, "remedies": [], "source": "none"})

    return JSONResponse({"remedies": out})


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


# run with uvicorn run:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("run:app", host="0.0.0.0", port=PORT, reload=True)
