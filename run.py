import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from rapidfuzz import process, fuzz
import redis
import json

# Load environment variables
load_dotenv()

# Flask setup
app = Flask(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Redis setup (optional caching)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(redis_url)

# Load remedies data
remedies_data = [
    {"symptom": "headache", "remedy": "Drink water, rest, and take paracetamol if needed."},
    {"symptom": "fever", "remedy": "Stay hydrated, rest, and take acetaminophen if temperature is high."},
    {"symptom": "cold", "remedy": "Drink warm fluids and take steam inhalation."},
    {"symptom": "stomach ache", "remedy": "Eat light food and avoid oily meals."},
    {"symptom": "cough", "remedy": "Drink honey with warm water and rest your voice."}
]


def ai_diagnose(symptom_text):
    """Diagnose symptoms using Gemini API with fallback logic."""
    cache_key = f"diagnosis:{symptom_text.lower()}"

    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        print("🔁 Cache hit")
        return json.loads(cached)

    print("💡 Cache miss – querying Gemini...")
    model = genai.GenerativeModel("gemini-pro")
    prompt = f"""
    You are a professional doctor assistant AI.
    Given the following symptoms: "{symptom_text}",
    provide a short and clear probable diagnosis and possible home remedies.
    """
    response = model.generate_content(prompt)
    diagnosis = response.text.strip()

    redis_client.setex(cache_key, 3600, json.dumps(diagnosis))
    return diagnosis


def find_remedy(symptom_text):
    """Find the closest remedy using fuzzy matching."""
    symptoms = [item["symptom"] for item in remedies_data]
    best_match, score, idx = process.extractOne(symptom_text, symptoms, scorer=fuzz.partial_ratio)
    if score > 60:
        return remedies_data[idx]["remedy"]
    return "No direct remedy found. Please consult a doctor."


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/diagnose", methods=["GET", "POST"])
def diagnose():
    if request.method == "POST":
        user_input = request.form.get("symptoms")
        if not user_input:
            return render_template("diagnose.html", error="Please enter symptoms.")

        ai_response = ai_diagnose(user_input)
        remedy = find_remedy(user_input)

        return render_template("result.html", diagnosis=ai_response, remedy=remedy, symptoms=user_input)

    return render_template("diagnose.html")


@app.route("/remedies")
def remedies():
    return render_template("remedies.html", remedies=remedies_data)


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    data = request.get_json()
    if not data or "symptoms" not in data:
        return jsonify({"error": "Missing symptoms"}), 400

    user_input = data["symptoms"]
    ai_response = ai_diagnose(user_input)
    remedy = find_remedy(user_input)

    return jsonify({"diagnosis": ai_response, "remedy": remedy})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
