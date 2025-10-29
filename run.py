import os
import json
import traceback
from urllib.parse import quote, unquote

from flask import Flask, render_template, request, jsonify, redirect, url_for
from rapidfuzz import fuzz
import redis

# Optional Gemini imports (if you don't want to enable Gemini, app still works)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

app = Flask(__name__)

# ---------- Optional Redis ----------
redis_url = os.environ.get("REDIS_URL")
redis_client = None
if redis_url:
    try:
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
        print("✅ Connected to Redis")
    except Exception as e:
        print("⚠️ Redis disabled (connection failed):", e)
        redis_client = None
else:
    print("⚠️ No REDIS_URL found. Redis disabled.")

# ---------- Configure Gemini if present ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY and GEMINI_AVAILABLE:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ Gemini configured")
else:
    if GEMINI_API_KEY and not GEMINI_AVAILABLE:
        print("⚠️ google-generativeai library missing; install it to use Gemini fallback.")
    else:
        print("⚠️ No GEMINI_API_KEY provided; Gemini fallback disabled.")

# ---------- Load local disease DB ----------
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "diseases.json")
if os.path.exists(DB_PATH):
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            DISEASE_DB = json.load(f)
        except Exception:
            DISEASE_DB = []
            print("⚠️ Failed to load database/diseases.json - invalid JSON")
else:
    DISEASE_DB = []
    print("⚠️ database/diseases.json not found; DB is empty. Gemini fallback will be used when available.")


def normalize_symptom_text(s):
    return s.strip().lower()


def score_against_disease(user_symptoms, disease_symptoms):
    """
    user_symptoms: list[str] (normalized)
    disease_symptoms: list[str] (original from DB)
    Returns: score between 0..100
    We'll compute per-user-symptom best fuzzy match to disease_symptoms and average.
    """
    if not disease_symptoms:
        return 0.0
    scores = []
    for us in user_symptoms:
        best = 0
        for ds in disease_symptoms:
            # normalize disease symptom
            ds_norm = ds.strip().lower()
            # use partial_ratio to handle substrings; use token_sort_ratio for multi-word
            s1 = fuzz.partial_ratio(us, ds_norm)
            s2 = fuzz.token_sort_ratio(us, ds_norm)
            local_best = max(s1, s2)
            if local_best > best:
                best = local_best
        scores.append(best)
    # average of per-symptom bests
    avg = sum(scores) / len(scores)
    return float(avg)


def top_matches_from_db(user_input_list, top_n=10):
    """
    Returns list of dicts: {"Disease": name, "Score": float(0-100)}
    """
    results = []
    for entry in DISEASE_DB:
        disease_name = entry.get("Disease", "Unknown")
        disease_symptoms = entry.get("Symptom", [])  # list
        # compute score
        s = score_against_disease(user_input_list, disease_symptoms)
        results.append({"Disease": disease_name, "Score": round(s, 2)})
    # sort desc
    results_sorted = sorted(results, key=lambda x: x["Score"], reverse=True)
    return results_sorted[:top_n]


def gemini_query_for_diseases(symptoms_text, top_n=10):
    """
    Ask Gemini for top N possible diseases for given symptoms.
    Returns list of {"Disease": name, "Score": float}
    """
    if not GEMINI_API_KEY or not GEMINI_AVAILABLE:
        return []

    prompt = f"""You are a medical assistant. Given the following symptoms (short): "{symptoms_text}", 
return a JSON array of up to {top_n} possible diseases with a confidence percentage (0-100). 
Format exactly as a JSON array of objects like:
[{{"Disease": "Name1", "Score": 87.5}}, {{"Disease": "Name2", "Score": 65.2}}]
Do NOT include explanatory text outside the JSON.
If you are unsure, give approximate percentages.
"""
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        text = getattr(response, "text", None) or str(response)
        # try to find a JSON array inside text
        import re
        match = re.search(r"(\[\s*\{.*\}\s*\])", text, re.S)
        json_text = match.group(1) if match else text
        parsed = json.loads(json_text)
        # ensure list of dicts with Disease and Score
        parsed_clean = []
        for item in parsed:
            name = item.get("Disease") or item.get("disease") or str(item)
            score = float(item.get("Score") or item.get("score") or 0)
            parsed_clean.append({"Disease": name, "Score": round(score, 2)})
        return parsed_clean[:top_n]
    except Exception as e:
        print("⚠️ Gemini disease query failed:", e)
        return []


def gemini_query_for_remedies(disease_name):
    """
    Ask Gemini to provide home remedies for a disease.
    Returns a string (short remedies).
    """
    if not GEMINI_API_KEY or not GEMINI_AVAILABLE:
        return "No remedies available (Gemini not configured)."
    prompt = f"""You are a professional medical assistant. Provide concise, safe home remedies and
basic non-prescription care suggestions for someone who likely has: "{disease_name}".
Return the answer as plain text, short bullet points (3-6 items). Avoid prescribing medication.
"""
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        text = getattr(response, "text", None) or str(response)
        return text.strip()
    except Exception as e:
        print("⚠️ Gemini remedy query failed:", e)
        return "No remedies available (Gemini query failed)."


# ---------- Routes ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/diagnose")
def diagnose():
    return render_template("diagnose.html")


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """
    Accepts JSON: {"symptoms": "fever, cough"} or {"symptoms": ["fever","cough"]}
    Returns: {"source":"db"|"gemini"|"mixed", "results":[{"Disease":..,"Score":..},...]}
    """
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Empty request"}), 400
        raw = payload.get("symptoms") or payload.get("symptom") or ""
        # normalize input into list of strings
        if isinstance(raw, list):
            user_sym_list = [normalize_symptom_text(s) for s in raw if s]
            symptoms_text = ", ".join(user_sym_list)
        else:
            # raw string, comma separated
            parts = [p.strip() for p in str(raw).split(",") if p.strip()]
            user_sym_list = [normalize_symptom_text(p) for p in parts]
            symptoms_text = ", ".join(user_sym_list)

        if len(user_sym_list) == 0:
            return jsonify({"error": "No symptoms provided"}), 400

        # cache key
        cache_key = f"diagnose:{symptoms_text}"
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    return jsonify({"source": "cache", "results": json.loads(cached.decode("utf-8"))})
                except Exception:
                    pass

        # compute matches from DB
        db_matches = top_matches_from_db(user_sym_list, top_n=50)  # compute more, we'll choose top10
        # decide threshold: if top db match score >= 50 -> use DB results
        top_db_score = db_matches[0]["Score"] if db_matches else 0

        results = []
        source = "db"
        if top_db_score >= 40:
            # return top 10 from DB
            results = db_matches[:10]
            source = "db"
        else:
            # fallback to Gemini if available
            gem = gemini_query_for_diseases(symptoms_text, top_n=10)
            if gem:
                results = gem
                source = "gemini"
            else:
                # return best efforts from DB (still top 10 even if low)
                results = db_matches[:10]
                source = "db"

        # cache
        if redis_client:
            try:
                redis_client.setex(cache_key, 3600, json.dumps(results))
            except Exception:
                pass

        return jsonify({"source": source, "results": results})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/remedies")
def remedies():
    """
    Query param: ?disease=Name%20Here
    """
    disease = request.args.get("disease", "")
    if not disease:
        return redirect(url_for("diagnose"))
    disease = unquote(disease)
    # try local simple mapping (you can create a local remedies DB later)
    local_remedy_db = {
        # a few quick local examples; Gemini will be used if not present
        "Common Cold": "Rest, warm fluids, steam inhalation, honey for cough.",
        "Flu": "Hydration, rest, paracetamol for fever, consult doctor if breathless.",
        "COVID-19": "Isolation, monitor oxygen, seek medical care if breathing difficulty.",
        "Asthma": "Use inhaler as prescribed; avoid triggers; seek urgent care if severe.",
        "Pneumonia": "See a doctor — antibiotics may be required; rest and fluids.",
    }
    remedy_text = local_remedy_db.get(disease)
    source = "local"
    if not remedy_text:
        # attempt cached
        cache_key = f"remedy:{disease}"
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    remedy_text = cached.decode("utf-8")
                    source = "cache"
                except Exception:
                    remedy_text = None
        if not remedy_text:
            # use Gemini
            gem_rem = gemini_query_for_remedies(disease)
            remedy_text = gem_rem
            source = "gemini" if gem_rem else "none"
            if redis_client and gem_rem:
                try:
                    redis_client.setex(cache_key, 86400, gem_rem)
                except Exception:
                    pass

    return render_template("remedies.html", disease=disease, remedies=remedy_text, source=source)


# simple health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # disable reloader in production environment
    app.run(host="0.0.0.0", port=port)
