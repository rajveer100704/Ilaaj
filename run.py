import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

# ------------------------------------------------------------
# Load environment variables
# ------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 8000))
TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", 10))

if not API_KEY or not API_KEY.startswith("AI"):
    raise RuntimeError("❌ GEMINI_API_KEY not found or invalid in .env file")

genai.configure(api_key=API_KEY)

# ------------------------------------------------------------
# Initialize FastAPI app
# ------------------------------------------------------------
app = FastAPI(title="🧠 Ilaaj - Smart AI Health Assistant", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Helper: Gemini API Wrapper
# ------------------------------------------------------------
async def call_gemini(prompt: str, timeout: float = TIMEOUT) -> str:
    """Safely call Gemini in async mode."""
    loop = asyncio.get_running_loop()

    def sync_call():
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return response.text or ""
        except Exception as e:
            print("❌ Gemini API call failed:", e)
            raise HTTPException(status_code=500, detail=f"Gemini error: {str(e)}")

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, sync_call), timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini request timed out")

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "🚀 Smart AI Diagnose API running!"}

@app.post("/api/diagnose")
async def diagnose(request: Request):
    data = await request.json()
    symptoms = data.get("symptoms", "").strip()
    limit = int(data.get("limit", 3))

    if not symptoms:
        raise HTTPException(status_code=400, detail="No symptoms provided")

    # Prompt to get structured output
    prompt = f"""
    You are a professional AI health assistant. 
    Based on the following symptoms: {symptoms}.
    List the top {limit} most likely diseases in structured JSON.

    Each entry must have:
    - "disease": name of the disease
    - "confidence": estimated likelihood (in %)
    - "description": a short summary (2–3 lines)
    - "remedies": a list of top 5 home or first-aid remedies

    Example format:
    {{
      "results": [
        {{
          "disease": "Flu",
          "confidence": "85%",
          "description": "A viral infection causing fever, cough, and fatigue.",
          "remedies": ["Rest well", "Drink warm fluids", "Take paracetamol", "Steam inhalation", "Stay hydrated"]
        }}
      ]
    }}
    Return strictly valid JSON — no markdown, no explanation, no extra text.
    """

    raw_response = await call_gemini(prompt)

    # Parse JSON safely even if Gemini adds extra text
    try:
        json_start = raw_response.find("{")
        json_end = raw_response.rfind("}")
        cleaned = raw_response[json_start:json_end + 1]
        parsed = json.loads(cleaned)
        return parsed
    except Exception as e:
        print("⚠️ Gemini returned unstructured text. Raw output:", raw_response)
        raise HTTPException(status_code=500, detail="Gemini response unstructured")

@app.post("/api/remedies")
async def remedies(request: Request):
    data = await request.json()
    disease = data.get("disease", "").strip()

    if not disease:
        raise HTTPException(status_code=400, detail="No disease provided")

    prompt = f"""
    You are an AI health advisor.
    List the top 5 scientifically valid and safe home remedies or lifestyle tips for managing {disease}.
    Respond only as JSON:
    {{
      "disease": "{disease}",
      "remedies": ["Remedy 1", "Remedy 2", "Remedy 3", "Remedy 4", "Remedy 5"]
    }}
    """

    raw_response = await call_gemini(prompt)
    try:
        json_start = raw_response.find("{")
        json_end = raw_response.rfind("}")
        cleaned = raw_response[json_start:json_end + 1]
        parsed = json.loads(cleaned)
        return parsed
    except Exception as e:
        print("⚠️ Failed to parse remedies:", raw_response)
        raise HTTPException(status_code=500, detail="Gemini returned invalid JSON for remedies")

# ------------------------------------------------------------
# Run the app
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
