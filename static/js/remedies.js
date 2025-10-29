// static/js/remedies.js
document.addEventListener("DOMContentLoaded", function () {
  const fetchBtn = document.getElementById("fetch-remedies");
  const diseaseInput = document.getElementById("disease");
  const area = document.getElementById("remedies-area");

  async function fetchFor(diseases) {
    area.innerHTML = "<div class='text-gray-500 p-4'>Loading remedies…</div>";
    try {
      const body = { diseases: diseases };
      const res = await fetch("/api/remedies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      const rems = data.remedies || [];
      if (!rems.length) {
        area.innerHTML = "<div class='text-gray-500 p-4'>No remedies available.</div>";
        return;
      }
      // render
      area.innerHTML = "";
      rems.forEach(function (r) {
        const card = document.createElement("div");
        card.className = "border rounded p-4 bg-slate-50";
        const title = document.createElement("h3");
        title.className = "font-semibold text-indigo-700";
        title.textContent = r.disease;
        card.appendChild(title);

        const src = document.createElement("div");
        src.className = "text-xs italic text-gray-500 mb-2";
        src.textContent = r.source ? `Source: ${r.source}` : "";
        card.appendChild(src);

        if (Array.isArray(r.remedies) && r.remedies.length) {
          const ul = document.createElement("ul");
          ul.className = "list-disc pl-6 space-y-1 text-left";
          r.remedies.forEach(function (it) {
            const li = document.createElement("li");
            li.textContent = it;
            ul.appendChild(li);
          });
          card.appendChild(ul);
        } else {
          const p = document.createElement("div");
          p.className = "text-gray-600";
          p.textContent = "No remedies found for this disease.";
          card.appendChild(p);
        }

        area.appendChild(card);
      });
    } catch (e) {
      area.innerHTML = "<div class='text-red-500 p-4'>Failed to fetch remedies.</div>";
    }
  }

  fetchBtn.addEventListener("click", function () {
    const d = diseaseInput.value.trim();
    if (!d) {
      area.innerHTML = "<div class='text-gray-500 p-4'>Please type a disease name.</div>";
      return;
    }
    fetchFor([d]);
  });

  // If we have a query param ?disease=..., auto-fetch
  (function () {
    const params = new URLSearchParams(window.location.search);
    if (params.has("disease")) {
      const d = params.get("disease");
      if (d) {
        diseaseInput.value = decodeURIComponent(d);
        fetchFor([decodeURIComponent(d)]);
        return;
      }
    }
    // support multiple diseases param ?diseases=a,b,c
    if (params.has("diseases")) {
      const ds = params
        .get("diseases")
        .split(",")
        .map((s) => decodeURIComponent(s).trim())
        .filter(Boolean);
      if (ds.length) fetchFor(ds);
    }
  })();
});
