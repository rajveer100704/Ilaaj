from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import google.generativeai as genai

app = FastAPI()

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "🚀 Smart Health Diagnose API running!"}

@app.post("/api/diagnose")
async def diagnose(request: Request):
    data = await request.json()
    symptoms = data.get("symptoms", "")
    limit = data.get("limit", 3)  # Top 3 by default

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
        You are a medical AI assistant. Based on the following symptoms:
        {symptoms}
        List the top {limit} possible diseases with confidence percentage
        and one-line description. Return in JSON format:
        [
          {{
            "disease": "Name",
            "confidence": "85%",
            "description": "Short info",
            "remedies": ["remedy1", "remedy2", "remedy3", "remedy4", "remedy5"]
          }}
        ]
        """

        response = model.generate_content(prompt)
        return {"results": eval(response.text)}

    except Exception as e:
        print("❌ Gemini API call failed:", e)
        return {"error": str(e)}
