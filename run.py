import os
import json
import traceback
from urllib.parse import unquote

from flask import Flask, render_template, request, jsonify, redirect, url_for
from rapidfuzz import fuzz
import redis

# Try to import google generative ai SDK (optional)
try:
    import google.generativeai as genai
    GEMINI_SDK_AVAILABLE = True
except Exception:
    GEMINI_SDK_AVAILABLE = False

app = Flask(__name__)

# ---------- Redis (optional) ----------
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

# ---------- Gemini config (optional) ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# A prioritized list of candidate model IDs to try (keeps code robust)
GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "chat-bison-001"  # fallback name (older)
]

active_gemini_model = None
if GEMINI_API_KEY and GEMINI_SDK_AVAILABLE:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # We'll lazily try models when we need to call them
        print("✅ Gemini SDK configured (model will be probed at runtime).")
    except Exception as e:
        print("⚠️ Gemini configure failed:", e)
else:
    if GEMINI_API_KEY and not GEMINI_SDK_AVAILABLE:
        print("⚠️ GEMINI_API_KEY provided but google-generativeai lib is not installed.")
    else:
        print("⚠️ No GEMINI_API_KEY provided; Gemini fallback disabled.")


# ---------- Load database (diseases.json) ----------
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "diseases.json")
if os.path.exists(DB_PATH):
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            DISEASE_DB = json.load(f)
            print(f"✅ Loaded {len(DISEASE_DB)} diseases from database/diseases.json")
    except Exception as e:
        DISEASE_DB = []
        print("⚠️ Failed to parse database/diseases.json:", e)
else:
    DISEASE_DB = []
    print("⚠️ database/diseases.json not found; using small builtin sample.")
    # minimal fallback sample so app can return something
    DISEASE_DB = [
        {"Disease": "Common Cold", "Symptom": ["sneezing", "runny nose", "sore throat", "cough"]},
        {"Disease": "Flu", "Symptom": ["fever", "cough", "body aches"]},
        {"Disease": "COVID-19", "Symptom": ["fever", "cough", "shortness of breath"]},
        {"Disease": "Pneumonia", "Symptom": ["cough", "fever", "difficulty breathing"]},
        {"Disease": "Asthma", "Symptom": ["wheezing", "coughing", "shortness of breath"]}
    ]


# ---------- utilities ----------
def normalize_symptom_text(s):
    return s.strip().lower()


def score_against_disease(user_symptoms, disease_symptoms):
    """
    Score user_symptoms (list of normalized strings) against disease_symptoms (list).
    Returns float score 0..100.
    """
    if not disease_symptoms:
        return 0.0
    scores = []
    for us in user_symptoms:
        best = 0
        for ds in disease_symptoms:
            ds_norm = ds.strip().lower()
            s1 = fuzz.partial_ratio(us, ds_norm)
            s2 = fuzz.token_sort_ratio(us, ds_norm)
            local_best = max(s1, s2)
            if local_best > best:
                best = local_best
        scores.append(best)
    return float(sum(scores) / len(scores))


def top_matches_from_db(user_input_list, top_n=10):
    results = []
    for entry in DISEASE_DB:
        disease_name = entry.get("Disease", "Unknown")
        disease_symptoms = entry.get("Symptom", [])
        s = score_against_disease(user_input_list, disease_symptoms)
        results.append({"Disease": disease_name, "Score": round(s, 2)})
    results_sorted = sorted(results, key=lambda x: x["Score"], reverse=True)
    return results_sorted[:top_n]


# ---------- Gemini helper (robust to model names) ----------
def _try_gemini_generate(prompt, candidate_models=None):
    """
    Try generate_content using candidate_models in order.
    Returns text or raises.
    """
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        raise RuntimeError("Gemini not configured or SDK missing")

    candidates = candidate_models or GEMINI_MODEL_CANDIDATES
    last_exc = None
    for m in candidates:
        try:
            model = genai.GenerativeModel(m)
            resp = model.generate_content(prompt)
            text = getattr(resp, "text", None) or str(resp)
            # remember the working model
            global active_gemini_model
            active_gemini_model = m
            print(f"✅ Gemini model {m} worked.")
            return text
        except Exception as e:
            last_exc = e
            print(f"⚠️ Gemini model {m} failed:", e)
            continue
    # if none worked, raise the last one
    raise last_exc if last_exc else RuntimeError("No Gemini model available")


def gemini_query_for_diseases(symptoms_text, top_n=10):
    """
    Ask Gemini for top N diseases as JSON-like array.
    Returns list of dicts {"Disease":..., "Score":...} or [] on failure.
    """
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        return []

    prompt = (
        f"You are a medical assistant. Given these symptoms: \"{symptoms_text}\", "
        f"return a JSON array (no extra text) of up to {top_n} possible diseases "
        "with a confidence percentage 0-100, like: "
        '[{"Disease":"Name","Score":87.5},{"Disease":"Name2","Score":65.2}].'
    )
    try:
        raw = _try_gemini_generate(prompt, GEMINI_MODEL_CANDIDATES)
        # try extract JSON array if extra text present
        import re
        match = re.search(r"(\[\s*\{.*\}\s*\])", raw, re.S)
        json_text = match.group(1) if match else raw
        parsed = json.loads(json_text)
        results = []
        for it in parsed:
            name = it.get("Disease") or it.get("disease") or str(it)
            score = float(it.get("Score") or it.get("score") or 0)
            results.append({"Disease": name, "Score": round(score, 2)})
        return results[:top_n]
    except Exception as e:
        print("⚠️ Gemini disease query failed:", e)
        return []


def gemini_query_for_remedies(disease_name):
    if not GEMINI_API_KEY or not GEMINI_SDK_AVAILABLE:
        return None
    prompt = (
        f"You are a professional medical assistant. Provide 4-6 short, safe home remedies and "
        f"self-care recommendations for someone with: \"{disease_name}\". Keep it concise, avoid prescribing medication. "
        "Return plain text bullet points."
    )
    try:
        raw = _try_gemini_generate(prompt, GEMINI_MODEL_CANDIDATES)
        return raw.strip()
    except Exception as e:
        print("⚠️ Gemini remedy query failed:", e)
        return None


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
    Input JSON: {"symptoms": "cough, fever"} or {"symptoms": ["cough","fever"]}
    Response: {"source":"db"|"gemini"|"cache", "results":[{"Disease":..,"Score":..},...]}
    """
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Empty request"}), 400

        raw = payload.get("symptoms") or payload.get("symptom") or ""
        if isinstance(raw, list):
            parts = [str(x).strip() for x in raw if str(x).strip()]
        else:
            parts = [p.strip() for p in str(raw).split(",") if p.strip()]

        user_sym_list = [normalize_symptom_text(p) for p in parts]

        if not user_sym_list:
            return jsonify({"error": "No symptoms provided"}), 400

        symptoms_text = ", ".join(user_sym_list)
        cache_key = f"diagnose:{symptoms_text}"
        # Try cache
        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    return jsonify({"source": "cache", "results": json.loads(cached.decode("utf-8"))})
            except Exception:
                pass

        # DB scoring (compute a larger top list, then choose top 10)
        db_matches = top_matches_from_db(user_sym_list, top_n=50)
        top_db_score = db_matches[0]["Score"] if db_matches else 0.0

        results = []
        source = "db"
        # if DB top score is reasonably strong, use DB
        if top_db_score >= 40:
            results = db_matches[:10]
            source = "db"
        else:
            # try Gemini fallback
            gem = gemini_query_for_diseases(symptoms_text, top_n=10)
            if gem:
                results = gem
                source = "gemini"
            else:
                # fall back to DB even if scores low
                results = db_matches[:10]
                source = "db"

        # Cache results
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
    Expects ?disease=Name
    """
    disease = request.args.get("disease", "")
    if not disease:
        return redirect(url_for("diagnose"))
    disease = unquote(disease)

    # local remedies map (small)
    local_remedy_db = {
        "Common Cold": "Rest, warm fluids, steam inhalation, honey for cough.",
        "Flu": "Hydration, rest, paracetamol for fever (if advised), consult if breathless.",
        "COVID-19": "Isolation, monitor oxygen, seek medical care if breathing difficulty.",
        "Asthma": "Use inhaler as prescribed, avoid triggers."
    }
    remedy_text = local_remedy_db.get(disease)
    source = "local"
    if not remedy_text:
        # check cache
        cache_key = f"remedy:{disease}"
        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    remedy_text = cached.decode("utf-8")
                    source = "cache"
            except Exception:
                pass

    if not remedy_text:
        # try Gemini
        gem = gemini_query_for_remedies(disease)
        if gem:
            remedy_text = gem
            source = "gemini"
            if redis_client:
                try:
                    redis_client.setex(cache_key, 86400, gem)
                except Exception:
                    pass
        else:
            remedy_text = "No remedies available."

    return render_template("remedies.html", disease=disease, remedies=remedy_text, source=source)


# health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Do not enable debug in production
    app.run(host="0.0.0.0", port=port)
