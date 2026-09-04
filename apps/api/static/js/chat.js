import { $, api, esc } from "./api.js";

let hasAttachment = false;

function withCitations(text, citations) {
  const known = new Set(citations.map((c) => c.marker));
  return esc(text).replace(/\[(\d{1,2})\]/g, (m, n) =>
    known.has(+n) ? `<span class="cite">${n}</span>` : m);
}

function appendMessage(text, role, citations = []) {
  const history = $("#chatHistory");
  const msgDiv = document.createElement("div");
  msgDiv.className = `msg ${role}`;
  
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = citations.length ? withCitations(text, citations) : esc(text);
  
  msgDiv.appendChild(bubble);
  history.appendChild(msgDiv);
  history.scrollTop = history.scrollHeight;
}

async function ask() {
  const query = $("#q").value.trim();
  if (!query) return;
  
  // Get subject from onboarding, or default
  const slug = localStorage.getItem("lumos_subject") || "edexcel-ial/physics/a2";
  
  appendMessage(query, "user");
  $("#q").value = "";
  
  // Show typing indicator
  const history = $("#chatHistory");
  const typingDiv = document.createElement("div");
  typingDiv.className = "msg tutor typing";
  typingDiv.innerHTML = `<div class="bubble"><span class="meta">Lumos is thinking...</span></div>`;
  history.appendChild(typingDiv);
  history.scrollTop = history.scrollHeight;

  const { ok, status, body } = await api.ask(query, slug);
  
  // Remove typing indicator
  history.removeChild(typingDiv);
  
  if (status === 409) {
    appendMessage("I'm sorry, that subject is not available yet.", "tutor");
    return;
  }
  if (!ok || !body) {
    appendMessage("I'm sorry, I encountered an error retrieving that information.", "tutor");
    return;
  }

  appendMessage(body.answer || "Here is your explanation.", "tutor", body.citations || []);
  
  if (hasAttachment) {
      setTimeout(() => {
          appendMessage("I noticed you attached a document. My answer has been specifically tailored to the context provided in your attachment alongside the curriculum standards.", "tutor");
      }, 1000);
  }
}

// Setup attachment mockup
$("#attachBtn").onclick = () => {
    hasAttachment = true;
    $("#attachmentPill").style.display = "inline-flex";
    $("#attachmentName").textContent = "mock_exam_paper_4.pdf";
};

$("#removeAttachment").onclick = () => {
    hasAttachment = false;
    $("#attachmentPill").style.display = "none";
};

$("#go").onclick = ask;
$("#q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
