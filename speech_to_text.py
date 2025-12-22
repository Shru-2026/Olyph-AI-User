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
    # Local development fallback
    load_dotenv()


def transcribe_pcm(pcm_bytes: bytes, sample_rate=16000) -> str:
    """
    Transcribes raw PCM audio bytes using Azure Speech-to-Text.
    Works both locally and on Render.
    """

    speech_key = os.getenv("AZURE_SPEECH_KEY")
    speech_region = os.getenv("AZURE_SPEECH_REGION")

    if not speech_key or not speech_region:
        raise RuntimeError(
            "Azure Speech credentials not found. "
            "Check .env in Render Secret Files or local environment."
        )

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

    push_stream.write(pcm_bytes)
    push_stream.close()

    result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text.strip()

    return ""
