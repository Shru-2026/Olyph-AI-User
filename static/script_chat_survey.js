document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Chat + Survey + Live Speech-to-Text loaded");

  // -------------------------
  // DOM refs
  // -------------------------
  const chatBody = document.getElementById("chat-body");
  const buttonContainer = document.querySelector(".button-container");
  const homeButton = document.getElementById("homeBtn");
  const sendBtn = document.getElementById("sendBtn");
  const userInput = document.getElementById("userInput");
  const askBtn = document.getElementById("askBtn");
  const surveyBtn = document.getElementById("surveyBtn");
  const micBtn = document.getElementById("micBtn");

  const recordingBar = document.getElementById("recordingBar");
  const recordingTime = document.getElementById("recordingTime");
  const stopRecordingBtn = document.getElementById("stopRecordingBtn");

  const voicePreview = document.getElementById("voicePreview");
  const sendVoiceBtn = document.getElementById("sendVoiceBtn");
  const discardVoiceBtn = document.getElementById("discardVoiceBtn");

  let selectedMode = null;
  const form = "https://forms.gle/u4pRVf1bAWSbWJA7A";

  // -------------------------
  // Speech recognition
  // -------------------------
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition || null;

  let recognizer = null;
  let isRecording = false;
  let speechSessionId = 0;   // 🔥 CRITICAL FIX

  // -------------------------
  // Utils
  // -------------------------
  function addMessage(text, sender = "bot") {
    if (!chatBody) return;
    const div = document.createElement("div");
    div.className = sender === "bot" ? "bot-message" : "user-message";
    div.innerHTML = String(text).replace(/\n/g, "<br>");
    chatBody.appendChild(div);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function clearInputHard() {
    if (userInput) {
      userInput.value = "";
      userInput.blur();
      userInput.focus();
    }
  }

  function resetSpeechState() {
    speechSessionId++;   // 🔥 invalidate old events
    isRecording = false;

    if (recognizer) {
      try { recognizer.abort(); } catch {}
      try { recognizer.stop(); } catch {}
      recognizer = null;
    }

    if (recordingBar) recordingBar.style.display = "none";
    if (voicePreview) voicePreview.style.display = "none";

    clearInputHard();
  }

  function resetChat() {
    if (chatBody) chatBody.innerHTML = "";
    resetSpeechState();
    addMessage("👋 Hey! I'm OlyphAI. How can I help you today?");
    if (buttonContainer) buttonContainer.style.display = "flex";
    if (homeButton) homeButton.style.display = "none";
    selectedMode = null;
  }

  function handleSelection(mode) {
    resetSpeechState();
    selectedMode = mode;

    if (buttonContainer) buttonContainer.style.display = "none";
    if (homeButton) homeButton.style.display = "inline-block";

    if (mode === "ask") {
      addMessage("💬 You can now ask questions or use voice.");
    } else {
      addMessage("📝 Opening survey form...");
      window.open(form, "_blank");
    }
  }

  // -------------------------
  // Text chat
  // -------------------------
  async function sendChat() {
    if (!userInput || selectedMode !== "ask") return;

    const msg = userInput.value.trim();
    if (!msg) return;

    resetSpeechState();
    addMessage(msg, "user");

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
      const data = await res.json();
      addMessage(data.reply || "⚠️ No reply");
    } catch {
      addMessage("⚠️ Server error");
    }
  }

  // -------------------------
  // 🎤 Live Speech-to-Text (FIXED)
  // -------------------------
  function startRecording() {
    if (isRecording) return;

    if (selectedMode !== "ask") {
      addMessage("⚠️ Voice works only in chat mode.");
      return;
    }

    if (!SpeechRecognition) {
      addMessage("⚠️ Speech recognition not supported.");
      return;
    }

    resetSpeechState();     // 🔥 HARD RESET
    isRecording = true;

    const currentSession = speechSessionId;

    recognizer = new SpeechRecognition();
    recognizer.continuous = true;
    recognizer.interimResults = true;
    recognizer.lang = "en-IN";

    if (recordingBar) recordingBar.style.display = "block";
    if (recordingTime) recordingTime.innerText = "0";

    let seconds = 0;
    const timer = setInterval(() => {
      if (!isRecording || currentSession !== speechSessionId) {
        clearInterval(timer);
        return;
      }
      seconds++;
      if (recordingTime) recordingTime.innerText = seconds;
    }, 1000);

    recognizer.onresult = (event) => {
      if (!isRecording || currentSession !== speechSessionId) return;

      let text = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        text += event.results[i][0].transcript;
      }
      if (userInput) userInput.value = text.trim();
    };

    recognizer.onerror = () => resetSpeechState();
    recognizer.onend = () => {};

    recognizer.start();
  }

  function stopRecording() {
    if (!isRecording) return;
    isRecording = false;

    if (recognizer) {
      try { recognizer.stop(); } catch {}
    }

    if (recordingBar) recordingBar.style.display = "none";
    if (voicePreview) voicePreview.style.display = "block";
  }

  async function sendVoice() {
    if (!userInput) return;

    const finalText = userInput.value.trim();
    if (!finalText) {
      addMessage("⚠️ No speech detected.");
      return;
    }

    resetSpeechState();
    addMessage(finalText, "user");

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: finalText })
      });
      const data = await res.json();
      addMessage(data.reply || "⚠️ No reply");
    } catch {
      addMessage("⚠️ Server error");
    }
  }

  // -------------------------
  // Bind events
  // -------------------------
  if (sendBtn) sendBtn.onclick = sendChat;
  if (micBtn) micBtn.onclick = startRecording;
  if (stopRecordingBtn) stopRecordingBtn.onclick = stopRecording;
  if (sendVoiceBtn) sendVoiceBtn.onclick = sendVoice;
  if (discardVoiceBtn) discardVoiceBtn.onclick = resetSpeechState;

  if (askBtn) askBtn.onclick = () => handleSelection("ask");
  if (surveyBtn) surveyBtn.onclick = () => handleSelection("survey");
  if (homeButton) homeButton.onclick = resetChat;

  resetChat();
});
