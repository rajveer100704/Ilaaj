# run.py
import os
import json
import traceback
from typing import List, Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Use google generative AI client
try:
    import google.generativeai as genai  # google-generativeai package
except Exception:
    genai = None

from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY") or None
PORT = int(os.getenv("PORT", "8000"))

app = FastAPI(title="Ilaaj — AI Health Companion (Gemini)")

# mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Configure Gemini if available
if genai and GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
    except Exception:
        # keep genai but warn
        genai = None

# helper: robust parse JSON list from LLM text
def extract_json_array(text: str) -> Optional[Any]:
    """Try to parse JSON. If direct parse fails, extract first [...] substring and parse."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    # direct parse
    try:
        parsed = json.loads(text)
        return parsed
    except Exception:
        pass
    # find first bracketed array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            substring = text[start:end+1]
            parsed = json.loads(substring)
            return parsed
        except Exception:
            pass
    return None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Input: {"symptoms":"fever, cough", "top_n": 3}
    Returns: {"results":[{"disease":"X","score":87.5,...},...], "source":"gemini"}
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    symptoms = data.get("symptoms", "")
    top_n = int(data.get("top_n", 3) or 3)
    top_n = max(1, min(20, top_n))

    if not (isinstance(symptoms, str) and symptoms.strip()):
        return JSONResponse({"results": [], "source": "none"})

    # If Gemini not configured, return a helpful error
    if not genai:
        return JSONResponse({"results": [], "source": "gemini_error", "error": "Gemini not configured"}, status_code=500)

    # Build a clear prompt instructing Gemini to return a JSON array
    prompt = (
        "You are a medical-assistant style model tasked to suggest likely conditions given user symptoms.\n"
        "Important: RETURN ONLY a JSON array (no extra text) containing up to "
        f"{top_n} objects. Each object must have keys: \"disease\" (string), \"score\" (number percentage 0..100), "
        "\"explain\" (short 10-25 word explanation). Example:\n"
        '[{"disease":"Flu","score":78.5,"explain":"Fever and body aches match typical influenza."}, ...]\n\n'
        f"User symptoms: \"{symptoms}\".\n"
        "Give the most likely conditions first, concise and realistic percentages (do not invent impossible values). "
        "If unsure, output lower confidence numbers and include common non-specific things like 'General viral infection'."
    )

    try:
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or str(resp)
        parsed = extract_json_array(text)
        results = []
        if isinstance(parsed, list):
            for item in parsed[:top_n]:
                if isinstance(item, dict):
                    name = item.get("disease") or item.get("label") or "Unknown Condition"
                    try:
                        score = float(item.get("score", 0) or 0.0)
                    except Exception:
                        score = 0.0
                    explain = item.get("explain") or item.get("reason") or ""
                    results.append({"disease": str(name), "score": round(score, 2), "explain": str(explain)})
    except Exception:
        traceback.print_exc()
        return JSONResponse({"results": [], "source": "gemini_error", "error": "Gemini request failed"}, status_code=500)

    # If Gemini returned nothing parseable, fail gracefully
    if not results:
        return JSONResponse({"results": [], "source": "gemini_error", "error": "Could not parse Gemini output"}, status_code=500)

    return JSONResponse({"results": results, "source": "gemini"})


@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Input: {"disease":"Name"}
    Returns: {"remedies":[{"disease":"Name","remedies":[..],"source":"gemini"}]}
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    disease = None
    if "disease" in data and isinstance(data["disease"], str):
        disease = data["disease"].strip()

    if not disease:
        return JSONResponse({"remedies": []})

    if not genai:
        return JSONResponse({"remedies": [{"disease": disease, "remedies": [], "source": "gemini_error", "error": "Gemini not configured"}]}, status_code=500)

    # Build a safety-first prompt for remedies
    prompt = (
        "You are an assistant that provides safe, non-prescriptive home remedies and self-care suggestions for a given condition.\n"
        "Important: RETURN ONLY a JSON array of strings (no objects, no commentary). Each string should be a short sentence (8-20 words) "
        "and MUST be non-prescriptive (no dosages, no medication instructions). Use gentle language and include 'seek medical care' if condition is serious.\n\n"
        f"Condition: \"{disease}\".\n"
        "Return up to 6 suggestions. Example: [\"Rest and hydrate.\", \"Use a cool compress for swelling.\"]"
    )

    try:
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or str(resp)
        parsed = extract_json_array(text)
        if isinstance(parsed, list):
            # ensure strings
            remedies = [str(x).strip() for x in parsed if str(x).strip()]
            if remedies:
                res_obj = {"disease": disease, "remedies": remedies, "source": "gemini"}
                return JSONResponse({"remedies": [res_obj]})
    except Exception:
        traceback.print_exc()
        return JSONResponse({"remedies": [{"disease": disease, "remedies": [], "source": "gemini_error", "error": "Gemini request failed"}]}, status_code=500)

    # fallback: no remedies parsed
    return JSONResponse({"remedies": [{"disease": disease, "remedies": [], "source": "gemini_error"}]})


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=PORT, reload=True)
