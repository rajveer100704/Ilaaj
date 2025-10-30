// static/js/diagnose.js
document.addEventListener("DOMContentLoaded", function () {
  const diagnoseBtn = document.getElementById("diagnose-btn");
  const openFullBtn = document.getElementById("openfull-btn");
  const textarea = document.getElementById("symptoms");
  const status = document.getElementById("diagnose-status");
  const resultsSection = document.getElementById("results");
  const resultsTableBody = document.querySelector("#results-table tbody");
  const remedyPanel = document.getElementById("remedy-panel");
  const remedyTitle = document.getElementById("remedy-title");
  const remedyBody = document.getElementById("remedy-body");
  const remedyClose = document.getElementById("remedy-close");
  const startBtn = document.getElementById("start-diagnosis");

  function setStatus(msg, isError = false) {
    status.textContent = msg;
    status.style.color = isError ? "crimson" : "";
  }

  function clearResults() {
    resultsTableBody.innerHTML = "";
    resultsSection.classList.add("hidden");
  }

  function renderResults(results) {
    resultsTableBody.innerHTML = "";
    if (!results || !results.length) {
      resultsTableBody.innerHTML = `<tr><td colspan="3" class="muted">No confident matches found.</td></tr>`;
      resultsSection.classList.remove("hidden");
      return;
    }
    results.forEach((r, idx) => {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.innerHTML = `<div style="font-weight:600">${r.disease}</div><div class="muted" style="font-size:13px">${r.explain || ""}</div>`;
      const tdScore = document.createElement("td");
      tdScore.innerHTML = `<div style="font-weight:600">${Number(r.score).toFixed(2)}%</div>`;
      const tdAction = document.createElement("td");
      const viewBtn = document.createElement("button");
      viewBtn.className = "small-btn";
      viewBtn.textContent = "View remedies";
      viewBtn.dataset.disease = r.disease;
      viewBtn.addEventListener("click", () => fetchRemediesFor(r.disease));
      tdAction.appendChild(viewBtn);

      tr.appendChild(tdName);
      tr.appendChild(tdScore);
      tr.appendChild(tdAction);
      resultsTableBody.appendChild(tr);
    });
    resultsSection.classList.remove("hidden");
  }

  function showSpinner(msg = "Loading…") {
    setStatus(msg);
  }

  async function callDiagnose(symptoms, topN = 3) {
    clearResults();
    remedyPanel.classList.add("hidden");
    setStatus("");
    if (!symptoms || !symptoms.trim()) {
      setStatus("Please enter symptoms (comma separated).", true);
      return;
    }
    showSpinner("Diagnosing...");
    try {
      const resp = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptoms, top_n: topN })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        setStatus("Server error while diagnosing.", true);
        console.error("diagnose error", resp.status, txt);
        return;
      }
      const data = await resp.json();
      const arr = (data.results || []).map(x => ({
        disease: x.disease || "Unknown Condition",
        score: Number(x.score || 0),
        explain: x.explain || ""
      }));
      setStatus("");
      renderResults(arr.slice(0, topN));
    } catch (e) {
      console.error(e);
      setStatus("Failed to diagnose — network error.", true);
    }
  }

  async function fetchRemediesFor(disease) {
    remedyPanel.classList.add("hidden");
    remedyTitle.textContent = "";
    remedyBody.innerHTML = "";

    if (!disease) return;

    showSpinner("Fetching remedies...");
    try {
      const resp = await fetch("/api/remedies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disease })
      });
      if (!resp.ok) {
        setStatus("Server error while fetching remedies.", true);
        return;
      }
      const data = await resp.json();
      const list = (data.remedies && data.remedies[0]) ? data.remedies[0] : null;
      setStatus("");
      remedyTitle.textContent = disease;
      if (!list || !Array.isArray(list.remedies) || !list.remedies.length) {
        remedyBody.innerHTML = `<p class='muted'>No remedies found for this disease. Always consult a healthcare provider.</p>`;
      } else {
        const ul = document.createElement("ul");
        ul.style.paddingLeft = "18px";
        ul.style.lineHeight = "1.6";
        list.remedies.forEach(it => {
          const li = document.createElement("li");
          li.textContent = it;
          ul.appendChild(li);
        });
        const src = document.createElement("div");
        src.className = "muted";
        src.style.fontSize = "13px";
        src.style.marginTop = "10px";
        src.textContent = list.source ? `Source: ${list.source}` : "";
        remedyBody.innerHTML = "";
        remedyBody.appendChild(ul);
        remedyBody.appendChild(src);
      }
      remedyPanel.classList.remove("hidden");
      remedyPanel.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      console.error(e);
      setStatus("Failed to fetch remedies — network error.", true);
    }
  }

  diagnoseBtn.addEventListener("click", function () {
    const sym = textarea.value.trim();
    callDiagnose(sym, 3);
  });

  openFullBtn.addEventListener("click", function () {
    const sym = textarea.value.trim();
    callDiagnose(sym, 10);
  });

  remedyClose && remedyClose.addEventListener("click", function () {
    remedyPanel.classList.add("hidden");
  });

  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      diagnoseBtn.click();
    }
  });

  startBtn.addEventListener("click", function () {
    document.getElementById("diagnose").scrollIntoView({ behavior: "smooth" });
    textarea.focus();
  });

  (function () {
    const params = new URLSearchParams(window.location.search);
    if (params.has("symptoms")) {
      const s = params.get("symptoms");
      textarea.value = decodeURIComponent(s);
      callDiagnose(decodeURIComponent(s), 3);
    }
  })();
});
