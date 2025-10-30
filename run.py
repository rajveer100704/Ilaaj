import os
import json
import traceback
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

# -----------------------------------------------------------------------------
# Load environment
# -----------------------------------------------------------------------------
load_dotenv()

PORT = int(os.getenv("PORT", 8000))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# -----------------------------------------------------------------------------
# Optional Gemini setup
# -----------------------------------------------------------------------------
GENAI_AVAILABLE = False
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GENAI_AVAILABLE = True
except Exception as e:
    print("[WARN] Gemini not configured:", e)
    GENAI_AVAILABLE = False

# -----------------------------------------------------------------------------
# Optional Redis setup
# -----------------------------------------------------------------------------
redis_client = None
try:
    import redis.asyncio as redis
    redis_client = redis.from_url(REDIS_URL)
except Exception as e:
    print("[WARN] Redis not connected:", e)
    redis_client = None

# -----------------------------------------------------------------------------
# FastAPI setup
# -----------------------------------------------------------------------------
app = FastAPI(title="Ilaaj", description="AI-powered health diagnosis assistant")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------------
# Root page
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -----------------------------------------------------------------------------
# Diagnosis API (mock / basic)
# -----------------------------------------------------------------------------
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Simple diagnosis logic or ML call (replace with your AI model if needed)
    """
    try:
        data = await request.json()
        symptoms = str(data.get("symptoms", "")).lower().strip()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not symptoms:
        return JSONResponse({"error": "No symptoms provided"}, status_code=400)

    # Example mock AI diagnosis
    results = []
    try:
        if "fever" in symptoms:
            results = [
                {"disease": "Typhoid", "score": 87.5},
                {"disease": "Dengue", "score": 76.3},
                {"disease": "Malaria", "score": 70.1},
            ]
        elif "constipation" in symptoms:
            results = [
                {"disease": "Alzheimer's Disease", "score": 67.22},
                {"disease": "Epilepsy", "score": 67.22},
                {"disease": "Stroke", "score": 67.22},
            ]
        else:
            results = [
                {"disease": "Unknown Condition", "score": 50.0},
                {"disease": "General Weakness", "score": 45.0},
                {"disease": "Stress", "score": 40.0},
            ]
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"results": results})

# -----------------------------------------------------------------------------
# Gemini Remedies
# -----------------------------------------------------------------------------
async def call_gemini_for_remedies(disease_name: str):
    """
    Returns (parsed_list_or_None, source_string, error_msg_or_None)
    """
    if not GENAI_AVAILABLE:
        return None, "gemini_unavailable", "Gemini API not configured."

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        prompt = (
            f"You are a medical assistant. For the disease '{disease_name}', "
            "list up to 6 safe, non-prescriptive home remedies in JSON array format "
            "(e.g. [\"Stay hydrated\", \"Eat light meals\", \"Rest properly\"]). "
            "No explanations or extra text."
        )
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or str(resp)

        # Try JSON parsing
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                except Exception:
                    parsed = None

        if isinstance(parsed, list) and parsed:
            return parsed[:6], "gemini", None

        # fallback split lines
        lines = [l.strip("•*- \t") for l in text.splitlines() if l.strip()]
        if lines:
            return lines[:6], "gemini_text", None

        return None, "gemini_empty", f"No valid remedies returned: {text[:200]}"
    except Exception as e:
        return None, "gemini_error", str(e)

# -----------------------------------------------------------------------------
# Remedies API
# -----------------------------------------------------------------------------
@app.post("/api/remedies")
async def api_remedies(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    diseases = []
    if isinstance(data.get("diseases"), list):
        diseases = data["diseases"]
    elif isinstance(data.get("disease"), str):
        diseases = [data["disease"]]
    else:
        return JSONResponse({"remedies": [], "error": "No disease provided"})

    output = []
    overall_error = None

    for d in diseases:
        dn = str(d).strip()
        if not dn:
            continue

        # Check Redis cache
        if redis_client:
            try:
                cached = await redis_client.get(f"remedy:{dn.lower()}")
                if cached:
                    output.append(json.loads(cached))
                    continue
            except Exception:
                pass

        # Call Gemini
        parsed, src, err = await call_gemini_for_remedies(dn)
        if parsed:
            obj = {"disease": dn, "remedies": parsed, "source": src}
            output.append(obj)
            if redis_client:
                try:
                    await redis_client.set(f"remedy:{dn.lower()}", json.dumps(obj), ex=86400)
                except Exception:
                    pass
        else:
            output.append({"disease": dn, "remedies": [], "source": src, "error": err})
            overall_error = overall_error or err

    resp = {"remedies": output}
    if overall_error:
        resp["error"] = overall_error
    return JSONResponse(resp)

# -----------------------------------------------------------------------------
# Manual Gemini Test
# -----------------------------------------------------------------------------
@app.get("/api/test_gemini")
async def test_gemini():
    if not GENAI_AVAILABLE:
        return JSONResponse({"error": "Gemini not configured"})
    res, src, err = await call_gemini_for_remedies("flu")
    return JSONResponse({"result": res, "source": src, "error": err})

# -----------------------------------------------------------------------------
# Startup check
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print(f"✅ Ilaaj Server started on port {PORT}")
    if GENAI_AVAILABLE:
        print("✅ Gemini API ready")
    else:
        print("⚠️ Gemini API not configured — remedies may be empty.")
    if redis_client:
        try:
            await redis_client.ping()
            print("✅ Redis connected")
        except Exception as e:
            print("⚠️ Redis connection failed:", e)

# -----------------------------------------------------------------------------
# Run directly
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=PORT, reload=True)
