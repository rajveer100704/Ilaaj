// static/js/diagnose.js
const diagnoseBtn = document.getElementById("diagnoseBtn");
const symptomsInput = document.getElementById("symptoms");
const chatArea = document.getElementById("chatArea");

// helper to append chat message
function appendMsg(text, who="ai"){
  const div = document.createElement("div");
  div.classList.add("msg", who === "user" ? "user" : "ai");
  div.innerHTML = text;
  chatArea.appendChild(div);
  div.scrollIntoView({behavior:"smooth", block:"end"});
}

function appendSpinner(){
  const s = document.createElement("div");
  s.className = "spinner";
  s.id = "diag-spinner";
  chatArea.appendChild(s);
  s.scrollIntoView({behavior:"smooth"});
}

function removeSpinner(){
  const s = document.getElementById("diag-spinner");
  if(s) s.remove();
}

diagnoseBtn && diagnoseBtn.addEventListener("click", async () => {
  const raw = symptomsInput.value.trim();
  if(!raw) { alert("Please enter symptoms (comma separated)."); return; }

  // show user bubble
  appendMsg(`<strong>You:</strong> ${raw}`, "user");

  // show spinner
  appendSpinner();

  try {
    const resp = await fetch("/api/diagnose", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({symptoms: raw})
    });
    const data = await resp.json();
    removeSpinner();
    if(data.error){
      appendMsg(`<strong>Error:</strong> ${data.error}`);
      return;
    }
    const results = data.results || [];
    if(results.length === 0){
      appendMsg("No matches found.");
      return;
    }
    // show chat-style AI message with top 3 summary + cards for top 10
    let summary = `<strong>Top matches (showing top ${Math.min(results.length,10)}):</strong><br/>`;
    summary += "<ol>";
    for(let i=0;i<Math.min(3,results.length);i++){
      summary += `<li>${results[i].disease} — ${results[i].score}%</li>`;
    }
    summary += "</ol>";
    appendMsg(summary);

    // Add result cards
    const container = document.createElement("div");
    container.className = "results-grid";
    for(let i=0;i<Math.min(10, results.length); i++){
      const r = results[i];
      const card = document.createElement("div");
      card.className = "result-card";
      let remediesText = r.remedies && r.remedies.length ? (Array.isArray(r.remedies)? r.remedies.join(", ") : r.remedies) : "No dataset remedies (click to fetch).";
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;">
                          <div><strong>${i+1}. ${r.disease}</strong><div style="color:#556">${r.score}%</div></div>
                          <div><button class="btn primary small" data-disease="${encodeURIComponent(r.disease)}">Remedies</button></div>
                        </div>
                        <div style="margin-top:8px;color:#3b556b">${remediesText}</div>`;
      container.appendChild(card);
    }
    chatArea.appendChild(container);
    container.scrollIntoView({behavior:"smooth"});

    // attach click listeners for remedies buttons
    container.querySelectorAll("button[data-disease]").forEach(btn=>{
      btn.addEventListener("click", async (e)=>{
        const disease = decodeURIComponent(btn.getAttribute("data-disease"));
        btn.disabled = true;
        const placeholder = document.createElement("div");
        placeholder.innerHTML = `<div class="spinner" style="width:30px;height:30px;border-width:4px"></div>`;
        btn.parentElement.appendChild(placeholder);
        try {
          const rres = await fetch("/api/remedies", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({ diseases: [disease] })
          });
          const json = await rres.json();
          if(json.remedies && json.remedies.length){
            const rem = json.remedies[0];
            alert(`${rem.disease} — Remedies:\n\n${(Array.isArray(rem.remedies)? rem.remedies.join("\n- ") : rem.remedies)}`);
          } else {
            alert("No remedies returned.");
          }
        } catch(err){
          console.error(err);
          alert("Failed to fetch remedies.");
        } finally {
          placeholder.remove();
          btn.disabled = false;
        }
      });
    });

  } catch(err){
    removeSpinner();
    console.error(err);
    appendMsg("Server error. Try again later.");
  }
});
