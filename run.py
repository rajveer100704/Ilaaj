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

# Configure Gemini
genai.configure(api_key=API_KEY)

# ------------------------------------------------------------
# Initialize FastAPI app
# ------------------------------------------------------------
app = FastAPI(title="Smart Health Diagnose API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow frontend access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Utility: call Gemini safely
# ------------------------------------------------------------
async def call_gemini(prompt: str, timeout: float = TIMEOUT) -> str:
    """Run Gemini generation safely in async context."""
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
        return await asyncio.wait_for(loop.run_in_executor(None, sync_call), timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini API request timed out")

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "🚀 Smart Health Diagnose API running!"}

@app.post("/api/diagnose")
async def diagnose(request: Request):
    data = await request.json()
    symptoms = data.get("symptoms", "").strip()
    if not symptoms:
        raise HTTPException(status_code=400, detail="No symptoms provided")

    prompt = f"""
    You are an AI health assistant.
    Given these symptoms: {symptoms}.
    Return the top 3 most likely diseases with short descriptions and remedies.
    Respond strictly as JSON:
    {{
      "results": [
        {{"disease": "...", "description": "...", "remedy": "..."}},
        ...
      ]
    }}
    """

    raw_response = await call_gemini(prompt)
    try:
        # Try to parse JSON; if text is wrapped, extract JSON part
        json_start = raw_response.find("{")
        json_end = raw_response.rfind("}")
        cleaned = raw_response[json_start:json_end+1]
        parsed = json.loads(cleaned)
        return parsed
    except Exception as e:
        print("⚠️ JSON parsing failed, returning raw text:", e)
        return {"raw_output": raw_response}

# ------------------------------------------------------------
# Run server
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
