from flask import Flask, render_template, request
import google.generativeai as genai
import json
import re
import os
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)

# Retrieve the API key from environment variables
api_key = os.environ.get("api_key1")
if not api_key:
    raise ValueError("No API key found in environment variables.")

# Configure the Gemini API with the retrieved API key
genai.configure(api_key=api_key)

def load_database():
    """Load the disease dataset from a JSON file."""
    try:
        with open('database/disease_dataset.json') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def diagnose(symptoms):
    """Diagnose diseases based on the provided symptoms."""
    database = load_database()
    matched_diseases = []
    symptoms_set = {symptom.lower() for symptom in symptoms}  # Convert symptoms to lowercase

    for entry in database:
        disease_symptoms = {symptom.lower() for symptom in entry["Symptom"]}  # Convert symptoms in the database to lowercase
        if symptoms_set.issubset(disease_symptoms):
            matched_diseases.append(entry["Disease"])

    return matched_diseases

def format_bullet_points(text):
    """Convert numbered text into HTML unordered list."""
    text = re.sub(r'^##\s+', '', text, flags=re.MULTILINE)
    # Match numbered points without markdown
    pattern = r'(\d+\.\s)(.*?)(?=\d+\.\s|\Z)'
    items = re.findall(pattern, text, flags=re.DOTALL)
    
    li_elements = [f"<li>{item[1].strip()}</li>" for item in items]
    return f"<ul>\n" + "\n".join(li_elements) + "\n</ul>"

def get_remedies(disease):
    """Fetch and format remedies using Gemini API."""
    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        prompt = f'''
        List 10 precautions for {disease} in this exact format:
        1. [Precaution 1]
        2. [Precaution 2]
        ...
        10. [Precaution 10]
        '''
        response = model.generate_content(prompt)
        
        # Handle API errors (Result 2)
        if not response.candidates:
            return "Error: No response from API"
            
        text = response.candidates[0].content.parts[0].text
        return format_bullet_points(text)
        
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/', methods=['GET'])
@app.route('/index', methods=['GET'])
def index():
    """Render the home page."""
    return render_template('index.html')

@app.route('/diagnose', methods=['GET', 'POST'])
def diagnose_route():
    """Handle the diagnosis route."""
    diseases = None
    if request.method == 'POST':
        symptoms_input = request.form.get('Symptom')
        if symptoms_input:
            symptoms_list = [symptom.strip().lower() for symptom in symptoms_input.split(',')]  # Convert input to lowercase
            diseases = diagnose(symptoms_list)
    return render_template('diagnose.html', diseases=diseases)

@app.route('/remedies', methods=['GET', 'POST'])
def remedies_route():
    """Handle the remedies route."""
    selected_disease = None
    remedies = None
    if request.method == 'POST':
        selected_disease = request.form.get('Disease')
        if selected_disease:
            remedies = get_remedies(selected_disease)
    return render_template('remedies.html', selected_disease=selected_disease, remedies=remedies)

if __name__ == '__main__':
    app.run(debug=True)
