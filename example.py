import pandas as pd
import os
import json

# Define the paths for input and output folders
input_folder = 'D:/Coding(2)/NLP/Datasets'
output_folder = 'C:/Users/anipr/OneDrive/Desktop/Disease'
input_filename = 'dieseases.csv'
output_filename = 'dataset1.json'

# Construct the full paths for input and output files
input_file_path = os.path.join(input_folder, input_filename)
output_file_path = os.path.join(output_folder, output_filename)

# Read the CSV file
df = pd.read_csv(input_file_path)

# Ensure the 'Symptom' columns are converted to strings and to lowercase
df['Symptom1'] = df['Symptom1'].astype(str).str.lower()
df['Symptom2'] = df['Symptom2'].astype(str).str.lower()
df['Symptom3'] = df['Symptom3'].astype(str).str.lower()

# Concatenate the symptoms into a list for each row
df['Symptom'] = df[['Symptom1', 'Symptom2', 'Symptom3']].apply(
    lambda x: [s.strip().replace('\\', '') for s in [x['Symptom1'], x['Symptom2'], x['Symptom3']] if pd.notna(s)],
    axis=1
)

# Drop the original columns if you no longer need them
df.drop(columns=['Symptom1', 'Symptom2', 'Symptom3'], inplace=True)

# Rename the column and convert to lowercase
df = df.rename(columns={'Dieseases': 'Disease'})
# df['Disease'] = df['Disease'].astype(str).str.lower()

# Convert the DataFrame to a JSON format with the desired structure
data = df.to_dict(orient='records')

# Format each record to match the desired JSON structure
formatted_data = []
for record in data:
    formatted_record = {
        "Disease": record.get('Disease', 'unknown'),  # Convert to lowercase
        "Symptom": [s.lower().replace('"', '') for s in record.get('Symptom', [])]  # Convert values to lowercase and remove extra quotes
    }
    formatted_data.append(formatted_record)

# Save the JSON data to a file
with open(output_file_path, 'w') as json_file:
    json.dump(formatted_data, json_file, indent=4, ensure_ascii=False)

print(f"File has been edited and saved to {output_file_path}")
