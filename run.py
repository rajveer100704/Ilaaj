# run.py
import os
import json
import asyncio
import re
import traceback
from typing import List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# load env
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PORT = int(os.getenv("PORT", "8000"))
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "10"))

# optional list of safe model names to try in order.
MODEL_CANDIDATES = [
    "gemini-1.5-pro",        # try high-capacity
    "gemini-1.5",            # fallback
    "gemini-1.5-flash",      # fallback
    "gemini-1.5-pro-latest"
]

# try to import google generative ai
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    else:
        genai = None
except Exception:
    genai = None

app = FastAPI(title="Ilaaj — AI Health Companion")

# allow local browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def extract_json(text: str):
    """
    Extract the first JSON object/array from text.
    Returns parsed object or None.
    """
    if not text:
        return None
    # quick attempts
    text = text.strip()
    # try direct json
    try:
        return json.loads(text)
    except Exception:
        pass

    # find first {...} or [...]
    # greedy match for balanced braces is complex; use regex to find braces then attempt incremental parse
    # find array first
    arr_match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if arr_match:
        candidate = arr_match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            # try to progressively shrink trailing characters
            pass

    obj_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if obj_match:
        candidate = obj_match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # fallback: try to extract lines like - {"disease": "X", "score": 12}
    json_like = re.findall(r"\{[^}]*\}", text, flags=re.DOTALL)
    for j in json_like:
        try:
            return json.loads(j)
        except Exception:
            continue

    return None


async def call_gemini_with_models(prompt: str, timeout: float = GEMINI_TIMEOUT) -> str:
    """
    Try calling Gemini with a list of candidate models. Return text response.
    Raises Exception on failure (or HTTPException for timeouts).
    """
    if genai is None:
        raise RuntimeError("Gemini client not configured (missing google.generativeai).")

    loop = asyncio.get_running_loop()

    def run_model(model_name: str):
        # run inside executor (sync) - call genai SDK
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            # SDK object might expose .text or similar
            text = getattr(resp, "text", None)
            if text is None:
                # fallback to string
                text = str(resp)
            return text
        except Exception as e:
            # bubble up
            raise

    last_exc = None
    for m in MODEL_CANDIDATES:
        try:
            # run in threadpool with timeout
            text = await asyncio.wait_for(loop.run_in_executor(None, run_model, m), timeout=timeout)
            # successful call
            return text
        except asyncio.TimeoutError as te:
            last_exc = te
            # try next model
        except Exception as e:
            last_exc = e
            # try next model
    # all failed
    if isinstance(last_exc, asyncio.TimeoutError):
        raise asyncio.TimeoutError("Gemini calls timed out for all models.")
    raise RuntimeError(f"Gemini failed for all models. Last error: {last_exc}")


# ----------------------
# Pages
# ----------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})


@app.get("/remedies", response_class=HTMLResponse)
async def remedies_page(request: Request):
    # expects ?disease=...
    return templates.TemplateResponse("remedies.html", {"request": request})


# ----------------------
# API endpoints
# ----------------------
@app.post("/api/diagnose")
async def api_diagnose(request: Request):
    """
    Body: {"symptoms":"cough, fever", "mode":"short" or "full"}
    Returns: {"results":[{"disease":..., "score":..., "description":...},...], "source":"gemini"}
    """
    if genai is None:
        return JSONResponse({"error": "Gemini client not available or GEMINI_API_KEY missing"}, status_code=500)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    symptoms = (payload.get("symptoms") or "").strip()
    mode = payload.get("mode", "short")
    if not symptoms:
        return JSONResponse({"results": [], "error": "No symptoms provided"}, status_code=400)

    k = 3 if mode != "full" else 10

    # Prompt: instruct Gemini to return ONLY JSON array
    prompt = (
        "You are a helpful, cautious assistant (non-prescriptive). "
        "Given user symptoms, return ONLY a JSON array (no extra commentary) containing up to "
        f"{k} objects with keys: 'disease' (short name), 'score' (confidence as number 0-100), "
        "'description' (one short sentence). Example:\n"
        '[{"disease":"Flu","score":78.5,"description":"..."}]\n\n'
        f"Symptoms: {symptoms}\n\n"
        "If you can't be confident, still return plausible possibilities but keep confidence values reasonable."
    )

    try:
        raw = await call_gemini_with_models(prompt)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Gemini timeout"}, status_code=504)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": "Gemini error", "detail": str(e)}, status_code=500)

    parsed = extract_json(raw)
    results = []
    if isinstance(parsed, list):
        for item in parsed[:k]:
            if isinstance(item, dict) and "disease" in item:
                # normalize
                disease = str(item.get("disease") or "")
                score = item.get("score") or item.get("confidence") or 0
                try:
                    score = float(score)
                except Exception:
                    score = 0.0
                desc = str(item.get("description") or item.get("desc") or "")
                results.append({"disease": disease, "score": round(score, 2), "description": desc})
    else:
        # parsing failed; return raw output in field so front-end can show it for debugging
        return JSONResponse({"error": "Could not parse Gemini output", "raw": raw}, status_code=500)

    return JSONResponse({"results": results, "source": "gemini"})


@app.post("/api/remedies")
async def api_remedies(request: Request):
    """
    Body: {"disease":"Influenza"} or {"diseases":["A","B"]}
    Returns: {"remedies":[{"disease":"...","remedies":["..",".."], "source":"gemini"}]}
    """
    if genai is None:
        return JSONResponse({"error": "Gemini client not available"}, status_code=500)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    diseases = []
    if "diseases" in payload and isinstance(payload["diseases"], list):
        diseases = payload["diseases"]
    elif "disease" in payload and payload["disease"]:
        diseases = [payload["disease"]]
    else:
        return JSONResponse({"remedies": []})

    out = []
    for d in diseases:
        dn = str(d).strip()
        if not dn:
            continue
        prompt = (
            "You are a responsible assistant. Provide up to 6 safe, "
            "non-prescriptive, self-care remedies or home-care suggestions for the condition: "
            f"'{dn}'. Return ONLY a JSON array of short strings, e.g. [\"Rest and hydrate\",\"Paracetamol as directed\",...]."
        )
        try:
            raw = await call_gemini_with_models(prompt)
            parsed = extract_json(raw)
            remedies = parsed if isinstance(parsed, list) else []
            # keep only strings
            remedies2 = [str(r).strip() for r in remedies if isinstance(r, (str,))]
            out.append({"disease": dn, "remedies": remedies2, "source": "gemini"})
        except asyncio.TimeoutError:
            out.append({"disease": dn, "remedies": [], "source": "timeout"})
        except Exception as e:
            out.append({"disease": dn, "remedies": [], "error": str(e)})
    return JSONResponse({"remedies": out})


@app.get("/health")
async def health():
    return {"status": "ok", "gemini_configured": bool(genai and GEMINI_API_KEY)}

