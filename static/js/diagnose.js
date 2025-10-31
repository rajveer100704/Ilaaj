const API_URL = "http://127.0.0.1:8000/api/diagnose";

async function fetchDiagnosis(limit) {
  const symptoms = document.getElementById("symptoms").value.trim();
  const resultDiv = document.getElementById("results");
  resultDiv.innerHTML = "<p>⏳ Diagnosing...</p>";

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symptoms, limit }),
    });

    if (!response.ok) throw new Error("Failed to fetch diagnosis");
    const data = await response.json();

    if (!data.results) {
      resultDiv.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      return;
    }

    resultDiv.innerHTML = `
      <h2>🧩 Possible Diseases (${data.results.length})</h2>
      ${data.results
        .map(
          (d) => `
        <div class="card">
          <h3>${d.disease}</h3>
          <p><strong>Confidence:</strong> ${d.confidence}</p>
          <p>${d.description}</p>
          <button onclick="viewRemedies('${encodeURIComponent(d.disease)}')">
            View Remedies
          </button>
        </div>`
        )
        .join("")}
    `;
  } catch (err) {
    resultDiv.innerHTML = `<p class="error">❌ ${err.message}</p>`;
  }
}

function viewRemedies(disease) {
  window.location.href = `/templates/remedies.html?disease=${disease}`;
}

document.getElementById("diagnoseBtn").addEventListener("click", () => fetchDiagnosis(3));
document.getElementById("viewFullBtn").addEventListener("click", () => fetchDiagnosis(10));
