# run.py
import os
import json
import asyncio
import traceback
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()
PORT = int(os.getenv("PORT", "8000"))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "10"))

# Import Gemini SDK if available
try:
    import google.generativeai as genai
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
except Exception:
    genai = None

app = FastAPI(title="Ilaaj - Gemini AI Health Companion")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Use a model known to support generate_content for SDK versions in requirements
MODEL_NAME = "gemini-1.5-flash"


def _extract_json(text: str):
    """Try parsing text as JSON; if not, extract JSON-ish substring and parse."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        # try to find first JSON array/object
        s = text
        # try array
        a = s.find("[")
        b = s.rfind("]") + 1
        if a != -1 and b != -1 and b > a:
            try:
                return json.loads(s[a:b])
            except Exception:
                pass
        # try object
        a = s.find("{")
        b = s.rfind("}") + 1
        if a != -1 and b != -1 and b > a:
            try:
                return json.loads(s[a:b])
            except Exception:
                pass
    return None


async def call_gemini_sync(prompt: str, timeout: float = TIMEOUT) -> str:
    """Call Gemini in a thread (to not block event loop). Return text string."""
    if not genai:
        raise RuntimeError("Gemini SDK not available or not configured")

    loop = asyncio.get_running_loop()

    def _call():
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)
        return getattr(resp, "text", str(resp))

    return await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=timeout)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})


@app.get("/remedies", response_class=HTMLResponse)
async def remedies_page(request: Request):
    # expects ?disease=Name
    return templates.TemplateResponse("remedies.html", {"request": request})


@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Input JSON: { "symptoms": "fever, cough", "mode": "short"|"full" }
    Output JSON: { "results":[{"disease":"X","score":87.5},...], "source":"gemini" }
    """
    if not genai or not GEMINI_KEY:
        return JSONResponse({"error": "Gemini not configured"}, status_code=500)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    symptoms = str(body.get("symptoms", "")).strip()
    mode = body.get("mode", "short")
    if not symptoms:
        return JSONResponse({"results": []})

    k = 3 if mode != "full" else 10

    # Clear JSON-only prompt with example
    prompt = (
        "You are a helper that only returns JSON. DO NOT RETURN ANY TEXT outside the JSON.\n\n"
        "Given short user symptoms, return a JSON array (only the array) of up to "
        f"{k} objects with these fields: 'disease' (string), 'score' (number 0-100).\n\n"
        "Example output:\n"
        '[{"disease":"Flu","score":78.5},{"disease":"Common Cold","score":45.2}]\n\n'
        "Now produce results for the following symptoms.\n\n"
        f"Symptoms: {symptoms}\n\n"
        "Return the JSON array only."
    )

    try:
        text = await call_gemini_sync(prompt)
        parsed = _extract_json(text)
        out = []
        if isinstance(parsed, list):
            for entry in parsed[:k]:
                if isinstance(entry, dict) and "disease" in entry:
                    try:
                        score = float(entry.get("score", 0) or 0.0)
                    except Exception:
                        score = 0.0
                    out.append({"disease": str(entry["disease"]).strip(), "score": round(score, 2)})
        return JSONResponse({"results": out, "source": "gemini"})
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Gemini timeout"}, status_code=504)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": "Gemini error", "detail": str(e)}, status_code=500)


@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Input JSON: { "disease": "Name" } or { "diseases": ["A","B"] }
    Output JSON: { "remedies":[{"disease":"Name","remedies":[..], "source":"gemini"}] }
    """
    if not genai or not GEMINI_KEY:
        return JSONResponse({"error": "Gemini not configured"}, status_code=500)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    diseases = []
    if isinstance(body.get("diseases"), list):
        diseases = body.get("diseases")
    elif body.get("disease"):
        diseases = [body.get("disease")]
    else:
        return JSONResponse({"remedies": []})

    output = []
    for d in diseases:
        d = str(d).strip()
        if not d:
            continue
        prompt = (
            "You are an assistant that returns JSON only (no extra text).\n\n"
            "For the medical condition name given, return a JSON array (only the array) of up to 6 safe, "
            "non-prescriptive, self-care or home-remedy suggestions (short strings). Do NOT suggest prescription-only medicines, "
            "do not give dosages, and include a short safety note as a separate final string if necessary.\n\n"
            f"Condition: {d}\n\n"
            "Example output:\n"
            '["Rest and hydrate", "Use a warm compress", "Seek medical care if high fever persists"]\n\n'
            "Return the JSON array only."
        )
        try:
            text = await call_gemini_sync(prompt)
            parsed = _extract_json(text)
            remedies = parsed if isinstance(parsed, list) else []
            # sanitize strings
            remedies = [str(r).strip() for r in remedies if str(r).strip()]
            output.append({"disease": d, "remedies": remedies, "source": "gemini"})
        except asyncio.TimeoutError:
            output.append({"disease": d, "remedies": [], "source": "timeout"})
        except Exception as e:
            output.append({"disease": d, "remedies": [], "source": "error", "error": str(e)})

    return JSONResponse({"remedies": output})


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "gemini": bool(genai and GEMINI_KEY)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=PORT, reload=True)
