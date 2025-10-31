# run.py
import os, json, asyncio, traceback
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# ───────────────────────────────────────────────
# Load environment variables
load_dotenv()
PORT = int(os.getenv("PORT", "8000"))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "10"))

# ───────────────────────────────────────────────
# Import Gemini API safely
try:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
except Exception:
    genai = None

# ───────────────────────────────────────────────
app = FastAPI(title="Ilaaj - Gemini AI Health Companion")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MODEL_NAME = "gemini-1.5-flash"  # ✅ always works (no 404 on current SDKs)

# ───────────────────────────────────────────────
def parse_json(text: str):
    """Extract JSON array/object from a text response."""
    try:
        return json.loads(text)
    except Exception:
        if "[" in text and "]" in text:
            start, end = text.find("["), text.rfind("]") + 1
            try:
                return json.loads(text[start:end])
            except Exception:
                pass
        if "{" in text and "}" in text:
            start, end = text.find("{"), text.rfind("}") + 1
            try:
                return json.loads(text[start:end])
            except Exception:
                pass
    return None

async def call_gemini(prompt: str, timeout: float = TIMEOUT) -> str:
    """Run Gemini generation in thread for async compatibility."""
    loop = asyncio.get_running_loop()

    def sync_call():
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)
        return getattr(resp, "text", str(resp))

    return await asyncio.wait_for(loop.run_in_executor(None, sync_call), timeout=timeout)

# ───────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
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

# ───────────────────────────────────────────────
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """Diagnose probable conditions."""
    if not (genai and GEMINI_KEY):
        return JSONResponse({"error": "Gemini API not configured"}, status_code=500)

    try:
        data = await request.json()
        symptoms = data.get("symptoms", "")
        mode = data.get("mode", "short")
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    k = 3 if mode != "full" else 10
    prompt = (
        f"You are a non-medical AI helper. Based on these symptoms, "
        f"return ONLY a JSON array (no text) of up to {k} conditions with fields "
        f"'disease' and 'score' (confidence 0–100).\n\n"
        f"Symptoms: {symptoms}"
    )

    try:
        text = await call_gemini(prompt)
        parsed = parse_json(text)
        results = []
        if isinstance(parsed, list):
            for x in parsed[:k]:
                if isinstance(x, dict) and "disease" in x:
                    results.append({
                        "disease": str(x["disease"]),
                        "score": float(x.get("score", 0))
                    })
        return JSONResponse({"results": results, "source": "gemini"})
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Gemini timeout"}, status_code=504)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": "Gemini error", "detail": str(e)}, status_code=500)

# ───────────────────────────────────────────────
@app.post("/api/remedies")
async def api_remedies(request: Request):
    """Get remedies for given diseases."""
    if not (genai and GEMINI_KEY):
        return JSONResponse({"error": "Gemini API not configured"}, status_code=500)

    try:
        data = await request.json()
        diseases = data.get("diseases") or [data.get("disease")]
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    out = []
    for d in diseases:
        if not d:
            continue
        prompt = (
            f"You are a helpful assistant. Give safe, non-medical, self-care remedies "
            f"for the condition '{d}'. Return ONLY a JSON array of short strings."
        )
        try:
            text = await call_gemini(prompt)
            parsed = parse_json(text)
            remedies = parsed if isinstance(parsed, list) else []
            out.append({"disease": d, "remedies": remedies, "source": "gemini"})
        except asyncio.TimeoutError:
            out.append({"disease": d, "remedies": [], "source": "timeout"})
        except Exception as e:
            out.append({"disease": d, "remedies": [], "error": str(e)})

    return JSONResponse({"remedies": out})

# ───────────────────────────────────────────────
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "gemini": bool(genai and GEMINI_KEY)})

# ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=PORT, reload=True)
