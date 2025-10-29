// static/js/diagnose.js
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("diagnose-btn");
  const textarea = document.getElementById("symptoms");
  const status = document.getElementById("diagnose-status");
  const resultsSec = document.getElementById("results");
  const matches = document.getElementById("matches");
  const detailed = document.getElementById("detailed");

  async function doDiagnose() {
    const text = textarea.value.trim();
    if (!text) {
      status.textContent = "Please enter symptoms.";
      return;
    }
    status.textContent = "Diagnosing…";
    matches.innerHTML = "";
    detailed.innerHTML = "";
    resultsSec.classList.add("hidden");

    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptoms: text }),
      });
      const data = await res.json();
      status.textContent = "";

      const results = data.results || [];
      if (!results.length) {
        resultsSec.classList.remove("hidden");
        matches.innerHTML = "<li>No confident matches found.</li>";
        return;
      }

      resultsSec.classList.remove("hidden");
      results.slice(0, 10).forEach((r, idx) => {
        const li = document.createElement("li");
        li.innerHTML = `
          <div class="p-3 rounded bg-white shadow-sm flex justify-between items-start">
            <div>
              <div class="font-semibold text-sky-700">${r.disease}</div>
              <div class="text-sm text-slate-600 mt-1">Confidence: ${r.score}%</div>
            </div>
            <div>
              <button data-disease="${encodeURIComponent(r.disease)}" class="rem-btn text-sm px-3 py-1 border rounded text-sky-600">Remedies</button>
            </div>
          </div>
        `;
        matches.appendChild(li);

        // small detailed card
        const card = document.createElement("div");
        card.className = "border rounded p-4 bg-white";
        card.innerHTML = `<div class="font-semibold">${idx+1}. ${r.disease}</div><div class="text-sm text-slate-600">${r.score}%</div>`;
        detailed.appendChild(card);
      });

      document.querySelectorAll(".rem-btn").forEach((b) => {
        b.addEventListener("click", function () {
          const disease = decodeURIComponent(this.getAttribute("data-disease"));
          const q = encodeURIComponent(disease);
          window.location.href = "/remedies?disease=" + q;
        });
      });
    } catch (e) {
      status.textContent = "Failed to diagnose.";
      console.error(e);
    }
  }

  btn.addEventListener("click", doDiagnose);
  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doDiagnose();
    }
  });
});
