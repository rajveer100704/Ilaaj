from flask import Flask, render_template, request, jsonify
import os
import redis
import traceback

app = Flask(__name__)

# ==========================
# Redis (Optional Integration)
# ==========================
redis_url = os.getenv("REDIS_URL")
redis_client = None

if redis_url:
    try:
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
        print("✅ Connected to Redis")
    except Exception as e:
        print("⚠️ Redis connection failed:", e)
        redis_client = None
else:
    print("⚠️ No REDIS_URL found. Redis disabled.")

# ==========================
# Routes
# ==========================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/diagnose")
def diagnose():
    return render_template("diagnose.html")

@app.route("/remedies")
def remedies():
    return render_template("remedies.html")

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """
    This endpoint handles the illness prediction logic.
    Called from diagnose.html via JS fetch("/api/diagnose").
    """
    try:
        data = request.get_json()
        symptoms = data.get("symptoms", "")
        if not symptoms:
            return jsonify({"error": "No symptoms provided"}), 400

        # Check cache first
        cache_key = f"diagnose:{symptoms}"
        if redis_client:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                return jsonify({"result": cached_result.decode('utf-8'), "cached": True})

        # Dummy diagnosis logic (replace with ML model later)
        result = f"Possible diagnosis based on symptoms: {symptoms.capitalize()}"

        # Cache the result
        if redis_client:
            redis_client.setex(cache_key, 3600, result)

        return jsonify({"result": result, "cached": False})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

#@app.errorhandler(404)
#def not_found(e):
#    return render_template("404.html"), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
