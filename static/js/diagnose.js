// static/js/diagnose.js
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("diagnose-btn");
  const openBtn = document.getElementById("openfull-btn");
  const textarea = document.getElementById("symptoms");
  const status = document.getElementById("status");
  const resultsEl = document.getElementById("results");

  function showStatus(msg, isError) {
    status.textContent = msg || "";
    status.style.color = isError ? "crimson" : "#333";
  }

  function renderResults(results, mode) {
    resultsEl.classList.remove("hidden");
    if (!results || !results.length) {
      resultsEl.innerHTML = "<div class='notice'>No matches found.</div>";
      return;
    }

    // short mode: show top 3 stacked
    if (mode === "short") {
      let html = "<div style='display:flex;gap:12px;flex-wrap:wrap'>";
      results.slice(0, 3).forEach(r => {
        html += `<div style="background:#fff;padding:12px;border-radius:10px;min-width:200px;box-shadow:0 4px 12px rgba(2,6,23,0.04)">
          <div style="font-weight:600;color:#0b86e6">${r.disease}</div>
          <div style="margin-top:8px">Confidence: ${r.score}%</div>
          <div style="margin-top:12px"><a class="btn" href="/remedies?disease=${encodeURIComponent(r.disease)}">View Remedies</a></div>
        </div>`;
      });
      html += "</div>";
      resultsEl.innerHTML = html;
      return;
    }

    // full mode: show table top 10
    let html = `<table class="table"><thead><tr><th>#</th><th>Disease</th><th>Confidence</th><th>Remedies</th></tr></thead><tbody>`;
    results.slice(0, 10).forEach((r, i) => {
      html += `<tr>
        <td>${i+1}</td>
        <td>${r.disease}</td>
        <td>${r.score}%</td>
        <td><a class="btn" href="/remedies?disease=${encodeURIComponent(r.disease)}">View Remedies</a></td>
      </tr>`;
    });
    html += "</tbody></table>";
    resultsEl.innerHTML = html;
  }

  async function doDiagnose(mode) {
    const text = textarea.value.trim();
    if (!text) {
      showStatus("Please enter symptoms (comma separated).", true);
      return;
    }
    showStatus("Analyzing — please wait...");
    resultsEl.classList.add("hidden");
    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptoms: text, mode: (mode === "full" ? "full" : "short") })
      });
      const data = await res.json();
      if (data.error) {
        showStatus("Error: " + data.error, true);
        return;
      }
      showStatus("");
      renderResults(data.results || [], mode === "short" ? "short" : "full");
    } catch (e) {
      console.error(e);
      showStatus("Failed to contact server.", true);
    }
  }

  btn?.addEventListener("click", () => doDiagnose("short"));
  openBtn?.addEventListener("click", () => doDiagnose("full"));

  // Allow Enter to submit (Ctrl+Enter for newline)
  textarea?.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doDiagnose("short");
    }
  });
});
