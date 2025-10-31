const REMEDY_API = "http://127.0.0.1:8000/api/remedies";

async function loadRemedies() {
  const urlParams = new URLSearchParams(window.location.search);
  const disease = decodeURIComponent(urlParams.get("disease"));
  document.getElementById("diseaseName").innerText = disease;

  const remedyList = document.getElementById("remedyList");
  remedyList.innerHTML = "<p>⏳ Fetching remedies...</p>";

  try {
    const response = await fetch(REMEDY_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disease }),
    });

    if (!response.ok) throw new Error("Failed to fetch remedies");
    const data = await response.json();

    if (!data.remedies) {
      remedyList.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      return;
    }

    remedyList.innerHTML = `
      <ul>
        ${data.remedies.map((r) => `<li>${r}</li>`).join("")}
      </ul>
    `;
  } catch (err) {
    remedyList.innerHTML = `<p class="error">❌ ${err.message}</p>`;
  }
}

window.onload = loadRemedies;
