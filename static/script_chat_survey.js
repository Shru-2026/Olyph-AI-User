document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Chat + Survey + Live Speech-to-Text loaded");

  // -------------------------
  // DOM refs (SAFE)
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
  const audioPlayback = document.getElementById("audioPlayback");
  const sendVoiceBtn = document.getElementById("sendVoiceBtn");
  const discardVoiceBtn = document.getElementById("discardVoiceBtn");

  let selectedMode = null;

  // -------------------------
  // Speech recognition
  // -------------------------
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition || null;

  let liveRecognizer = null;
  let liveTranscript = "";
  let isRecording = false;

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

  function resetChat() {
    if (chatBody) chatBody.innerHTML = "";
    addMessage("👋 Hey! I'm OlyphAI. How can I help you today?");
    if (buttonContainer) buttonContainer.style.display = "flex";
    if (homeButton) homeButton.style.display = "none";
    selectedMode = null;
    userInput && (userInput.value = "");
  }

  function handleSelection(mode) {
    selectedMode = mode;
    if (buttonContainer) buttonContainer.style.display = "none";
    if (homeButton) homeButton.style.display = "inline-block";

    if (mode === "ask") {
      addMessage("💬 You can now ask questions or use voice.");
      userInput && userInput.focus();
    } else {
      addMessage("📝 Opening survey form...");
      window.open("https://forms.gle/u4pRVf1bAWSbWJA7A", "_blank");
    }
  }

  // -------------------------
  // Text chat (UNCHANGED FLOW)
  // -------------------------
  async function sendChat() {
    if (!userInput || selectedMode !== "ask") return;

    const msg = userInput.value.trim();
    if (!msg) return;

    userInput.value = "";
    addMessage(msg, "user");

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
      const data = await res.json();
      addMessage(data.reply || "⚠️ No reply");
    } catch (err) {
      console.error(err);
      addMessage("⚠️ Server error");
    }
  }

  // -------------------------
  // 🎤 Live Speech-to-Text (UI ONLY)
  // -------------------------
  function startRecording() {
    if (isRecording) return;

    if (selectedMode !== "ask") {
      addMessage("⚠️ Voice works only in chat mode.");
      return;
    }

    if (!SpeechRecognition) {
      addMessage("⚠️ Speech recognition not supported in this browser.");
      return;
    }

    liveRecognizer = new SpeechRecognition();
    liveRecognizer.continuous = true;
    liveRecognizer.interimResults = true;
    liveRecognizer.lang = "en-IN";

    liveTranscript = "";
    isRecording = true;

    if (recordingBar) recordingBar.style.display = "block";
    if (voicePreview) voicePreview.style.display = "none";
    if (recordingTime) recordingTime.innerText = "0";

    let seconds = 0;
    const timer = setInterval(() => {
      if (!isRecording) return clearInterval(timer);
      seconds++;
      if (recordingTime) recordingTime.innerText = seconds;
    }, 1000);

    liveRecognizer.onresult = (event) => {
      let interim = "";
      let finalText = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const txt = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += txt + " ";
        } else {
          interim += txt;
        }
      }

      liveTranscript += finalText;
      if (userInput) {
        userInput.value = (liveTranscript + interim).trim();
      }
    };

    liveRecognizer.onerror = (e) => {
      console.error("Speech error:", e);
      stopRecording();
    };

    liveRecognizer.start();
  }

  function stopRecording() {
    if (!isRecording) return;
    isRecording = false;

    if (liveRecognizer) {
      liveRecognizer.stop();
      liveRecognizer = null;
    }

    if (recordingBar) recordingBar.style.display = "none";

    // Freeze final text
    if (userInput && liveTranscript) {
      userInput.value = liveTranscript.trim();
    }

    if (voicePreview) voicePreview.style.display = "block";
  }

  function discardRecording() {
    liveTranscript = "";
    if (userInput) userInput.value = "";
    if (voicePreview) voicePreview.style.display = "none";
  }

  // -------------------------
  // Send voice → EXISTING /ask
  // -------------------------
  async function sendVoice() {
    if (!userInput) return;

    const finalText = userInput.value.trim();
    if (!finalText) {
      addMessage("⚠️ No speech detected.");
      return;
    }

    addMessage(finalText, "user");

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: finalText })
      });
      const data = await res.json();
      addMessage(data.reply || "⚠️ No reply");
    } catch (err) {
      console.error(err);
      addMessage("⚠️ Server error");
    }

    discardRecording();
  }

  // -------------------------
  // Bind events (NULL SAFE)
  // -------------------------
  if (sendBtn) sendBtn.onclick = sendChat;
  if (micBtn) micBtn.onclick = startRecording;
  if (stopRecordingBtn) stopRecordingBtn.onclick = stopRecording;
  if (sendVoiceBtn) sendVoiceBtn.onclick = sendVoice;
  if (discardVoiceBtn) discardVoiceBtn.onclick = discardRecording;

  if (askBtn) askBtn.onclick = () => handleSelection("ask");
  if (surveyBtn) surveyBtn.onclick = () => handleSelection("survey");
  if (homeButton) homeButton.onclick = resetChat;

  resetChat();
});
