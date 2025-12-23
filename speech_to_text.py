# speech_to_text.py
import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# ----------------------------------
# Load .env from Render Secret Files
# ----------------------------------
ENV_PATH = "/etc/secrets/.env"

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
else:
    load_dotenv()


def transcribe_pcm(pcm_bytes: bytes, sample_rate=16000) -> str:
    """
    Transcribes raw PCM audio bytes using Azure Speech-to-Text.
    SAFE for repeated calls in Flask / Render.
    """

    speech_key = os.getenv("AZURE_SPEECH_KEY")
    speech_region = os.getenv("AZURE_SPEECH_REGION")

    if not speech_key or not speech_region:
        raise RuntimeError(
            "Azure Speech credentials not found. "
            "Check Render secret env or local .env."
        )

    recognizer = None
    push_stream = None
    audio_config = None

    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=speech_key,
            region=speech_region
        )
        speech_config.speech_recognition_language = "en-IN"

        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate,
            bits_per_sample=16,
            channels=1
        )

        push_stream = speechsdk.audio.PushAudioInputStream(stream_format)
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        # Push audio
        push_stream.write(pcm_bytes)
        push_stream.close()

        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text.strip()

        return ""

    finally:
        # 🔥 CRITICAL CLEANUP (fixes one-time-only bug)
        try:
            if recognizer:
                recognizer.stop_continuous_recognition()
                del recognizer
        except Exception:
            pass

        try:
            if audio_config:
                del audio_config
        except Exception:
            pass

        try:
            if push_stream:
                del push_stream
        except Exception:
            pass
