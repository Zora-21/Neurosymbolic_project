const API_BASE_URL = ""; // Relative path
let sessionId = localStorage.getItem("session_id") || crypto.randomUUID();
localStorage.setItem("session_id", sessionId);

const chatContainer = document.getElementById("chat-container");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const resetBtn = document.getElementById("reset-btn");
const currentAgentEl = document.getElementById("current-agent");
const patientDataEl = document.getElementById("patient-data-content");
const reportEl = document.getElementById("report-content");

// --- UTILS ---
function appendMessage(role, content, agent = null) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}`;

    // Simple Markdown parsing (bold, italic, lists)
    let formattedContent = content
        .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
        .replace(/\*(.*?)\*/g, '<i>$1</i>')
        .replace(/\n/g, '<br>');

    msgDiv.innerHTML = `
        <div class="message-content">
            ${formattedContent}
        </div>
    `;

    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function updatePatientData(data) {
    if (!data || Object.keys(data).length === 0) {
        patientDataEl.innerHTML = "<p><em>In attesa di dati...</em></p>";
        return;
    }

    let html = "";

    // Helper per creare sezioni
    const createSection = (title, items) => {
        if (!items || items.length === 0) return "";
        const list = items.map(i => `<li>${i}</li>`).join("");
        return `<div class="data-item"><span class="data-label">${title}</span><ul style="padding-left: 1.2rem; margin: 0;">${list}</ul></div>`;
    };

    html += createSection("Sintomi", data.symptoms);
    html += createSection("Durata", data.duration);
    html += createSection("Esclusioni", data.negative_findings);
    html += createSection("Farmaci", data.medications);
    html += createSection("Allergie", data.allergies);
    html += createSection("Storia Clinica", data.medical_history);

    if (data.vital_signs && Object.keys(data.vital_signs).length > 0) {
        html += `<div class="data-item"><span class="data-label">Parametri Vitali</span>`;
        for (const [k, v] of Object.entries(data.vital_signs)) {
            html += `<div><small>${k}:</small> <b>${v}</b></div>`;
        }
        html += `</div>`;
    }

    patientDataEl.innerHTML = html;
}

function updateReport(referto) {
    if (!referto || referto.length === 0) {
        reportEl.innerHTML = "<p><em>Nessun report disponibile.</em></p>";
        return;
    }

    let html = "";
    referto.forEach(item => {
        html += `
            <div class="report-section">
                <h3>${item.condition} (${item.probability})</h3>
                <p>${item.reasoning}</p>
            </div>
        `;
    });
    reportEl.innerHTML = html;
}

// --- IMAGE UPLOAD ---
const imageInput = document.getElementById("image-input");
const uploadBtn = document.getElementById("upload-btn");
const imagePreviewContainer = document.getElementById("image-preview-container");
const imagePreview = document.getElementById("image-preview");
const removeImageBtn = document.getElementById("remove-image-btn");

let currentImageBase64 = null;

uploadBtn.addEventListener("click", () => imageInput.click());

imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        currentImageBase64 = e.target.result.split(',')[1]; // Remove data:image/...;base64, prefix
        imagePreview.src = e.target.result;
        imagePreviewContainer.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
});

removeImageBtn.addEventListener("click", () => {
    imageInput.value = "";
    currentImageBase64 = null;
    imagePreview.src = "";
    imagePreviewContainer.classList.add("hidden");
});

// --- DRAG AND DROP ---
const chatColumn = document.querySelector('.chat-column');

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    chatColumn.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Highlight drop zone
['dragenter', 'dragover'].forEach(eventName => {
    chatColumn.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    chatColumn.addEventListener(eventName, unhighlight, false);
});

function highlight(e) {
    chatColumn.classList.add('drag-over');
}

function unhighlight(e) {
    chatColumn.classList.remove('drag-over');
}

// Handle dropped files
chatColumn.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length > 0 && files[0].type.startsWith('image/')) {
        handleFile(files[0]);
    }
}

function handleFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        currentImageBase64 = e.target.result.split(',')[1];
        imagePreview.src = e.target.result;
        imagePreviewContainer.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
}

// --- API CALLS ---
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text && !currentImageBase64) return; // Allow sending image without text if needed, or require text

    // UI Update
    if (currentImageBase64) {
        // Show image in chat
        const imgTag = `<img src="data:image/jpeg;base64,${currentImageBase64}" style="max-width: 200px; border-radius: 0.5rem; display: block; margin-bottom: 0.5rem;">`;
        appendMessage("user", imgTag + (text ? text : ""));
    } else {
        appendMessage("user", text);
    }

    userInput.value = "";
    userInput.disabled = true;
    sendBtn.disabled = true;

    // Clear image selection
    const imageToSend = currentImageBase64; // Store for sending
    imageInput.value = "";
    currentImageBase64 = null;
    imagePreview.src = "";
    imagePreviewContainer.classList.add("hidden");

    // Loading indicator
    const loadingId = "loading-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "message assistant";
    loadingDiv.innerHTML = "<em>Analisi in corso...</em>";
    chatContainer.appendChild(loadingDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    try {
        const payload = {
            message: text,
            session_id: sessionId
        };

        if (imageToSend) {
            payload.image_data = imageToSend;
        }

        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        // Remove loading
        document.getElementById(loadingId).remove();

        // 1. Handle Extra Messages (Router handoff)
        if (data.extra_messages) {
            data.extra_messages.forEach(msg => {
                appendMessage(msg.role, msg.content, msg.agent);
            });
        }

        // 2. Handle Main Response
        appendMessage("assistant", data.response, data.agent_type);

        // 3. Update UI State
        currentAgentEl.textContent = data.agent_type;
        updatePatientData(data.patient_data);
        updateReport(data.referto);

        if (data.is_final) {
            sessionId = crypto.randomUUID();
            localStorage.setItem("session_id", sessionId);
            appendMessage("system", "Sessione conclusa. Nuova sessione avviata.");
        }

    } catch (error) {
        console.error(error);
        document.getElementById(loadingId).remove();
        appendMessage("system", "Errore di connessione. Riprova.");
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

async function resetSession() {
    if (!confirm("Sei sicuro di voler cancellare la conversazione?")) return;

    try {
        await fetch(`${API_BASE_URL}/reset`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId })
        });
    } catch (e) { console.error(e); }

    sessionId = crypto.randomUUID();
    localStorage.setItem("session_id", sessionId);
    chatContainer.innerHTML = `
        <div class="message system">
            <div class="message-content">
                <strong>System:</strong> Sessione resettata.
            </div>
        </div>
    `;
    currentAgentEl.textContent = "Router";
    patientDataEl.innerHTML = "<p><em>In attesa di dati...</em></p>";
    reportEl.innerHTML = "<p><em>Nessun report disponibile.</em></p>";

    // Reset image state too
    imageInput.value = "";
    currentImageBase64 = null;
    imagePreview.src = "";
    imagePreviewContainer.classList.add("hidden");
}

// --- EVENTS ---
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
});
resetBtn.addEventListener("click", resetSession);
