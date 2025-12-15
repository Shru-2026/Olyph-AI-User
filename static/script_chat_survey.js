document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Chat + Survey + Voice recording loaded");

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
  const audioPlayback = document.getElementById("audioPlayback");
  const sendVoiceBtn = document.getElementById("sendVoiceBtn");
  const discardVoiceBtn = document.getElementById("discardVoiceBtn");

  let selectedMode = null;

  // -------------------------
  // Utils
  // -------------------------
  function addMessage(text, sender = "bot") {
    const div = document.createElement("div");
    div.className = sender === "bot" ? "bot-message" : "user-message";
    div.innerHTML = text.replace(/\n/g, "<br>");
    chatBody.appendChild(div);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function resetChat() {
    chatBody.innerHTML = "";
    addMessage("👋 Hey! I'm OlyphAI. How can I help you today?");
    buttonContainer.style.display = "flex";
    homeButton.style.display = "none";
    selectedMode = null;
  }

  function handleSelection(mode) {
    selectedMode = mode;
    buttonContainer.style.display = "none";
    homeButton.style.display = "inline-block";

    if (mode === "ask") {
      addMessage("💬 You can now ask questions or use voice.");
    } else {
      addMessage("📝 Opening survey form...");
      window.open("https://forms.gle/u4pRVf1bAWSbWJA7A", "_blank");
    }
  }

  // -------------------------
  // Text chat
  // -------------------------
  async function sendChat() {
    const msg = userInput.value.trim();
    if (!msg || selectedMode !== "ask") return;

    userInput.value = "";
    addMessage(msg, "user");

    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    });

    const data = await res.json();
    addMessage(data.reply || "⚠️ No reply");
  }

  // -------------------------
  // 🎤 Voice recording (PCM)
  // -------------------------
  let audioContext;
  let processor;
  let input;
  let micStream;
  let pcmChunks = [];
  let wavChunks = [];
  let timer;
  let seconds = 0;

  async function startRecording() {
    if (selectedMode !== "ask") {
      addMessage("⚠️ Voice works only in chat mode.");
      return;
    }

    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new AudioContext({ sampleRate: 16000 });

    input = audioContext.createMediaStreamSource(micStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);

    pcmChunks = [];
    wavChunks = [];
    seconds = 0;

    recordingBar.style.display = "block";
    voicePreview.style.display = "none";

    timer = setInterval(() => {
      seconds++;
      recordingTime.innerText = seconds;
    }, 1000);

    processor.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(data.length);

      for (let i = 0; i < data.length; i++) {
        pcm16[i] = Math.max(-1, Math.min(1, data[i])) * 0x7fff;
      }

      pcmChunks.push(new Uint8Array(pcm16.buffer));
      wavChunks.push(pcm16);
    };

    input.connect(processor);
    processor.connect(audioContext.destination);
  }

  function stopRecording() {
    clearInterval(timer);
    recordingBar.style.display = "none";

    processor.disconnect();
    input.disconnect();
    micStream.getTracks().forEach(t => t.stop());

    const wavBlob = createWavBlob(wavChunks, 16000);
    audioPlayback.src = URL.createObjectURL(wavBlob);
    voicePreview.style.display = "block";
  }

  function discardRecording() {
    voicePreview.style.display = "none";
    pcmChunks = [];
    wavChunks = [];
  }

  // -------------------------
  // ✅ SAFE Base64 Encoder (FIX)
  // -------------------------
  function uint8ToBase64(u8Arr) {
    let CHUNK_SIZE = 0x8000; // 32KB
    let index = 0;
    let result = '';
    let slice;

    while (index < u8Arr.length) {
      slice = u8Arr.subarray(index, index + CHUNK_SIZE);
      result += String.fromCharCode.apply(null, slice);
      index += CHUNK_SIZE;
    }
    return btoa(result);
  }

  // -------------------------
  // Send voice (FIXED)
  // -------------------------
  async function sendVoice() {
    if (!pcmChunks.length) {
      addMessage("⚠️ No audio recorded.");
      return;
    }

    addMessage("🎧 Processing voice…");

    const total = pcmChunks.reduce((a, b) => a + b.length, 0);
    const merged = new Uint8Array(total);
    let offset = 0;

    pcmChunks.forEach(chunk => {
      merged.set(chunk, offset);
      offset += chunk.length;
    });

    const base64Audio = uint8ToBase64(merged);

    console.log("📤 Sending audio", {
      bytes: merged.length,
      base64: base64Audio.length
    });

    try {
      const res = await fetch("/speech-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio: base64Audio,
          sampleRate: 16000
        })
      });

      const data = await res.json();
      console.log("📥 Backend response:", data);

      if (data.transcript) addMessage(data.transcript, "user");
      addMessage(data.reply || "⚠️ No reply");

    } catch (err) {
      console.error("❌ sendVoice error:", err);
      addMessage("⚠️ Failed to send voice.");
    }

    discardRecording();
  }

  // -------------------------
  // WAV helper (preview only)
  // -------------------------
  function createWavBlob(chunks, sampleRate) {
    const bufferLength = chunks.reduce((a, b) => a + b.length, 0);
    const buffer = new ArrayBuffer(44 + bufferLength * 2);
    const view = new DataView(buffer);

    let offset = 0;
    function writeString(s) {
      for (let i = 0; i < s.length; i++) {
        view.setUint8(offset++, s.charCodeAt(i));
      }
    }

    writeString("RIFF");
    view.setUint32(offset, 36 + bufferLength * 2, true); offset += 4;
    writeString("WAVEfmt ");
    view.setUint32(offset, 16, true); offset += 4;
    view.setUint16(offset, 1, true); offset += 2;
    view.setUint16(offset, 1, true); offset += 2;
    view.setUint32(offset, sampleRate, true); offset += 4;
    view.setUint32(offset, sampleRate * 2, true); offset += 4;
    view.setUint16(offset, 2, true); offset += 2;
    view.setUint16(offset, 16, true); offset += 2;
    writeString("data");
    view.setUint32(offset, bufferLength * 2, true); offset += 4;

    chunks.forEach(chunk => {
      chunk.forEach(sample => {
        view.setInt16(offset, sample, true);
        offset += 2;
      });
    });

    return new Blob([view], { type: "audio/wav" });
  }

  // -------------------------
  // Bind events
  // -------------------------
  sendBtn.onclick = sendChat;
  micBtn.onclick = startRecording;
  stopRecordingBtn.onclick = stopRecording;
  sendVoiceBtn.onclick = sendVoice;
  discardVoiceBtn.onclick = discardRecording;

  askBtn.onclick = () => handleSelection("ask");
  surveyBtn.onclick = () => handleSelection("survey");
  homeButton.onclick = resetChat;

  resetChat();
});
