const params = new URLSearchParams(window.location.search);
const disease = params.get("disease");
const remediesDiv = document.getElementById("remedies");

async function loadRemedies() {
  remediesDiv.innerHTML = "Loading remedies...";
  try {
    const res = await fetch("http://localhost:8000/api/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symptoms: disease, limit: 1 }),
    });
    const data = await res.json();
    if (data.results && data.results[0]) {
      const rems = data.results[0].remedies;
      remediesDiv.innerHTML = `
        <h2>Top Remedies for ${disease}</h2>
        <ul>${rems.map(r => `<li>${r}</li>`).join("")}</ul>
      `;
    } else {
      remediesDiv.innerHTML = "No remedies found.";
    }
  } catch (err) {
    remediesDiv.innerHTML = `<p style="color:red">Gemini API error</p>`;
  }
}

loadRemedies();
