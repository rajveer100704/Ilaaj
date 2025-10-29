from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
import google.generativeai as genai

# App setup
app = FastAPI(title="Ilaaj 🩺 | AI Health Assistant")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "database", "disease_dataset.json")

# Templates & static
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Load dataset
try:
    with open(DATA_PATH, "r") as f:
        disease_data = json.load(f)
except:
    disease_data = []
    print("⚠️ disease_dataset.json not found.")

# Gemini setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ============= Utility =============
def calculate_match(symptoms, disease_symptoms):
    match = len(set(symptoms) & set(disease_symptoms))
    return match / len(disease_symptoms) if disease_symptoms else 0

def get_top_diseases(symptom_text):
    symptoms = [s.strip().lower() for s in symptom_text.split(",") if s.strip()]
    scored = []
    for item in disease_data:
        score = calculate_match(symptoms, [s.lower() for s in item["symptoms"]])
        if score > 0:
            scored.append({
                "disease": item["disease"],
                "score": round(score * 100, 2),
                "remedies": item.get("remedies", [])
            })
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:10]

async def gemini_diagnose(symptom_text):
    prompt = f"""
    Given the symptoms: {symptom_text}.
    List top 10 likely diseases with estimated percentages.
    Respond as JSON: [{{"disease": "...", "score": 78.5}}]
    """
    try:
        resp = gemini_model.generate_content(prompt)
        return json.loads(resp.text)
    except:
        return []

async def gemini_remedies(disease_list):
    prompt = f"""
    For diseases: {', '.join(disease_list)}, suggest top 3 effective remedies.
    Respond as JSON: [{{"disease": "...", "remedies": ["...", "..."]}}]
    """
    try:
        resp = gemini_model.generate_content(prompt)
        return json.loads(resp.text)
    except:
        return []

# ============= Routes =============
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/diagnose", response_class=HTMLResponse)
async def diagnose_page(request: Request):
    return templates.TemplateResponse("diagnose.html", {"request": request})

@app.post("/diagnose", response_class=JSONResponse)
async def diagnose(symptoms: str = Form(...)):
    results = get_top_diseases(symptoms)
    if not results:
        results = await gemini_diagnose(symptoms)
    return {"results": results}

@app.get("/remedies", response_class=HTMLResponse)
async def remedies_page(request: Request):
    return templates.TemplateResponse("remedies.html", {"request": request})

@app.post("/remedies", response_class=JSONResponse)
async def remedies(symptoms: str = Form(...)):
    results = get_top_diseases(symptoms)
    if not results:
        results = await gemini_diagnose(symptoms)

    disease_names = [r["disease"] for r in results]
    remedies_data = []
    for d in disease_data:
        if d["disease"] in disease_names:
            remedies_data.append({"disease": d["disease"], "remedies": d.get("remedies", [])})
    if len(remedies_data) < len(disease_names):
        gemini_data = await gemini_remedies(disease_names)
        remedies_data.extend(gemini_data)
    return {"remedies": remedies_data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
