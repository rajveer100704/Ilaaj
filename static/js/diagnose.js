// static/js/diagnose.js
document.addEventListener("DOMContentLoaded", () => {
  const symptomsEl = document.getElementById("symptoms");
  const btnDiag = document.getElementById("btn-diagnose");
  const btnFull = document.getElementById("btn-full");
  const status = document.getElementById("status");
  const resultsDiv = document.getElementById("results");

  function showStatus(msg, isError=false){
    status.textContent = msg;
    status.style.color = isError ? "crimson" : "#0b84d9";
  }

  function clearResults(){
    resultsDiv.innerHTML = "";
    resultsDiv.classList.add("hidden");
  }

  function renderResults(items){
    resultsDiv.innerHTML = "";
    if (!items || !items.length){
      resultsDiv.innerHTML = "<div class='result-item'>No results</div>";
      resultsDiv.classList.remove("hidden");
      return;
    }
    items.forEach(it => {
      const el = document.createElement("div");
      el.className = "result-item";
      el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div class="result-title">${escapeHtml(it.disease)}</div>
            <div class="small-desc">${escapeHtml(it.description || "")}</div>
          </div>
          <div style="text-align:right">
            <div style="font-weight:700">${it.score}%</div>
            <button class="view-rem" data-disease="${encodeURIComponent(it.disease)}">View Remedies</button>
          </div>
        </div>
      `;
      resultsDiv.appendChild(el);
    });
    resultsDiv.classList.remove("hidden");

    // attach handlers
    document.querySelectorAll(".view-rem").forEach(b=>{
      b.addEventListener("click", ()=>{
        const d = decodeURIComponent(b.getAttribute("data-disease"));
        // open remedies page with query param
        window.location.href = `/remedies?disease=${encodeURIComponent(d)}`;
      });
    });
  }

  function escapeHtml(s){
    if (!s) return "";
    return s.replace(/[&<>"']/g, (c)=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c]);
  }

  async function doCall(mode){
    const symptoms = symptomsEl.value.trim();
    if (!symptoms){
      showStatus("Please enter symptoms (comma separated).", true);
      return;
    }
    clearResults();
    showStatus("Analyzing… this may take 2–8 seconds depending on API.", false);
    btnDiag.disabled = true; btnFull.disabled = true;
    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({symptoms: symptoms, mode: mode})
      });
      const data = await res.json();
      if (!res.ok){
        showStatus(data.error || JSON.stringify(data), true);
        return;
      }
      showStatus("");
      const results = data.results || [];
      renderResults(results);
    } catch (e) {
      console.error(e);
      showStatus("Failed to call server. See console.", true);
    } finally {
      btnDiag.disabled = false; btnFull.disabled = false;
    }
  }

  btnDiag.addEventListener("click", ()=> doCall("short"));
  btnFull.addEventListener("click", ()=> doCall("full"));
});
