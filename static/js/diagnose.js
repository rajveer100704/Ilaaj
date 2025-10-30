document.getElementById("diagnose-btn").addEventListener("click", () => runDiagnosis("top3"));
document.getElementById("openfull-btn").addEventListener("click", () => runDiagnosis("top10"));
const modal = document.getElementById("remediesModal");
const closeModal = document.getElementById("closeModal");
closeModal.onclick = () => modal.style.display = "none";

async function runDiagnosis(mode) {
    const symptoms = document.getElementById("symptoms").value.trim();
    const resultsDiv = document.getElementById("results");
    if (!symptoms) {
        resultsDiv.innerHTML = "<p>Please enter symptoms first.</p>";
        return;
    }

    resultsDiv.innerHTML = "<div class='loading'>Analyzing...</div>";

    const formData = new FormData();
    formData.append("symptoms", symptoms);
    formData.append("mode", mode);

    const res = await fetch("/api/diagnose", { method: "POST", body: formData });
    const data = await res.json();

    if (data.status === "success") {
        let html = `
        <table>
            <tr><th>Disease</th><th>Confidence</th><th>Action</th></tr>
        `;
        data.diseases.forEach(d => {
            html += `
            <tr>
                <td>${d.disease}</td>
                <td>${d.confidence}%</td>
                <td><button onclick="viewRemedies('${d.disease}')">View Remedies</button></td>
            </tr>`;
        });
        html += `</table>`;
        resultsDiv.innerHTML = html;
    } else {
        resultsDiv.innerHTML = `<p class="error">${data.message}</p>`;
    }
}

async function viewRemedies(disease) {
    const formData = new FormData();
    formData.append("disease", disease);

    const res = await fetch("/api/remedies", { method: "POST", body: formData });
    const data = await res.json();

    if (data.status === "success") {
        document.getElementById("remediesContent").innerHTML = `<p>${data.remedies}</p>`;
        modal.style.display = "block";
    } else {
        alert("Error: " + data.message);
    }
}
