// static/js/diagnose.js
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("diagnose-btn");
  const textarea = document.getElementById("symptoms");
  const status = document.getElementById("diagnose-status");
  const resultsSection = document.getElementById("results");
  const matchesList = document.getElementById("matches");
  const detailed = document.getElementById("detailed");

  async function doDiagnose() {
    const text = textarea.value.trim();
    if (!text) {
      status.textContent = "Please enter symptoms.";
      return;
    }
    status.textContent = "Analyzing…";
    matchesList.innerHTML = "";
    detailed.innerHTML = "";
    resultsSection.classList.add("hidden");

    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptoms: text }),
      });
      const data = await res.json();
      status.textContent = "";
      const results = data.results || [];
      if (!results || results.length === 0) {
        resultsSection.classList.remove("hidden");
        matchesList.innerHTML = "<li>No confident matches found.</li>";
        return;
      }

      resultsSection.classList.remove("hidden");
      // list top 10
      results.slice(0, 10).forEach(function (r, idx) {
        const li = document.createElement("li");
        li.className = "mb-2";
        li.innerHTML = `<div class="p-3 border rounded bg-slate-50">
          <div class="flex justify-between items-start">
            <div>
              <div class="font-semibold text-indigo-700">${r.disease}</div>
              <div class="text-sm text-gray-600 mt-1">Confidence: ${r.score}%</div>
            </div>
            <div class="ml-4">
              <button data-disease="${encodeURIComponent(r.disease)}" class="remedies-btn px-3 py-1 text-sm border rounded text-indigo-600">View Remedies</button>
            </div>
          </div>
        </div>`;
        matchesList.appendChild(li);

        // Detailed shorter card
        const card = document.createElement("div");
        card.className = "border rounded p-4 bg-slate-50";
        card.innerHTML = `<h4 class="font-semibold">${idx + 1}. ${r.disease}</h4>
                          <div class="text-sm text-gray-600">${r.score}%</div>`;
        detailed.appendChild(card);
      });

      // attach remedies buttons
      document.querySelectorAll(".remedies-btn").forEach(function (b) {
        b.addEventListener("click", function () {
          const disease = decodeURIComponent(this.getAttribute("data-disease"));
          // navigate to remedies page with query param (no popup)
          const q = encodeURIComponent(disease);
          window.location.href = "/remedies?disease=" + q;
        });
      });
    } catch (e) {
      status.textContent = "Failed to diagnose.";
    }
  }

  btn.addEventListener("click", doDiagnose);

  // support pressing Enter inside textarea for quick submit (Shift+Enter for newline)
  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doDiagnose();
    }
  });
});
