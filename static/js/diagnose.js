document.getElementById("diagnoseBtn").addEventListener("click", async () => {
  await fetchDiseases(3);
});

document.getElementById("openFullBtn").addEventListener("click", async () => {
  await fetchDiseases(10);
});

async function fetchDiseases(limit) {
  const symptoms = document.getElementById("symptomInput").value;
  const resultDiv = document.getElementById("results");
  resultDiv.innerHTML = "Diagnosing...";

  try {
    const res = await fetch("http://localhost:8000/api/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symptoms, limit }),
    });
    const data = await res.json();

    if (data.error) {
      resultDiv.innerHTML = `<p style="color:red">Error: ${data.error}</p>`;
      return;
    }

    let html = "<h3>Top Results</h3>";
    data.results.forEach((d, i) => {
      html += `
        <div class="disease-card">
          <h4>${i + 1}. ${d.disease} (${d.confidence})</h4>
          <p>${d.description}</p>
          <a href="remedies.html?disease=${encodeURIComponent(d.disease)}" class="btn">View Remedies</a>
        </div>
      `;
    });
    resultDiv.innerHTML = html;

  } catch (err) {
    resultDiv.innerHTML = `<p style="color:red">Error: Gemini API unreachable</p>`;
    console.error(err);
  }
}
