// static/js/remedies.js
const getRemediesBtn = document.getElementById("getRemediesBtn");
const diseaseInput = document.getElementById("diseaseInput");
const remediesArea = document.getElementById("remediesArea");

getRemediesBtn && getRemediesBtn.addEventListener("click", async () => {
  const disease = diseaseInput.value.trim();
  if(!disease) { alert("Enter disease name or use Diagnose first."); return; }
  remediesArea.innerHTML = "<div class='spinner'></div>";
  try {
    const res = await fetch("/api/remedies", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ diseases: [disease] })
    });
    const data = await res.json();
    remediesArea.innerHTML = "";
    if(data.remedies && data.remedies.length){
      const r = data.remedies[0];
      const card = document.createElement("div");
      card.className = "result-card";
      const remText = Array.isArray(r.remedies) ? r.remedies.join("\n") : r.remedies;
      card.innerHTML = `<h3>${r.disease}</h3><pre style="white-space:pre-wrap">${remText}</pre><p class="muted">Source: ${r.source}</p>`;
      remediesArea.appendChild(card);
    } else {
      remediesArea.innerHTML = "<p>No remedies found.</p>";
    }
  } catch(err){
    remediesArea.innerHTML = "<p>Failed to fetch remedies.</p>";
    console.error(err);
  }
});
