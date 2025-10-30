from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Static + Templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Gemini API setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})

@app.post("/api/diagnose")
async def diagnose(symptoms: str = Form(...), mode: str = Form("top3")):
    try:
        limit = 3 if mode == "top3" else 10
        prompt = f"""
        You are an intelligent medical diagnosis assistant.
        Based on the symptoms: {symptoms},
        return the top {limit} possible diseases in JSON format like:
        [
          {{"disease": "Disease Name", "confidence": 85}},
          ...
        ]
        Do not add explanations or markdown.
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        import json
        diseases = json.loads(text)
        return JSONResponse({"status": "success", "diseases": diseases})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

@app.post("/api/remedies")
async def get_remedies(disease: str = Form(...)):
    try:
        prompt = f"""
        You are a medical assistant. Provide 5 effective home or lifestyle remedies
        for treating or managing the disease: {disease}.
        Format as bullet points.
        """
        response = model.generate_content(prompt)
        return JSONResponse({"status": "success", "remedies": response.text})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
