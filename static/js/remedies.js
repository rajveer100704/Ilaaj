// static/js/remedies.js
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("fetch-remedies");
  const inp = document.getElementById("disease-input");
  const area = document.getElementById("remedies-area");

  function showAreaHtml(html){
    area.innerHTML = html;
  }

  async function fetchRemedies(disease){
    showAreaHtml("<div class='result-item'>Loading remedies…</div>");
    try {
      const res = await fetch("/api/remedies", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({disease: disease})
      });
      const data = await res.json();
      if (!res.ok){
        showAreaHtml(`<div class='result-item'>Error: ${data.error || JSON.stringify(data)}</div>`);
        return;
      }
      const arr = data.remedies || [];
      if (!arr.length){
        showAreaHtml(`<div class='result-item'>No remedies found.</div>`);
        return;
      }
      // show first (should be only one)
      const r = arr[0];
      const list = (r.remedies || []).map(s=>`<li>${escapeHtml(s)}</li>`).join("");
      const html = `
        <div class="result-item">
          <div class="result-title">${escapeHtml(r.disease)}</div>
          <div class="small-desc">Source: ${escapeHtml(r.source||"gemini")}</div>
          ${list ? `<ul style="margin-top:10px">${list}</ul>` : `<div class="small-desc" style="margin-top:8px">No remedies found.</div>`}
        </div>
      `;
      showAreaHtml(html);
    } catch (e){
      console.error(e);
      showAreaHtml("<div class='result-item'>Failed to fetch remedies. See console.</div>");
    }
  }

  function escapeHtml(s){
    if (!s) return "";
    return s.replace(/[&<>"']/g, (c)=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c]);
  }

  btn.addEventListener("click", ()=>{
    const d = inp.value.trim();
    if (!d){
      showAreaHtml("<div class='result-item'>Please type a disease name</div>");
      return;
    }
    fetchRemedies(d);
  });
});
