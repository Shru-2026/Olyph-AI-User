import os
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk

load_dotenv()

speech_config = speechsdk.SpeechConfig(
    subscription=os.getenv("AZURE_SPEECH_KEY"),
    region=os.getenv("AZURE_SPEECH_REGION")
)

# Indian English (recommended for you)
speech_config.speech_recognition_language = "en-IN"

audio_config = speechsdk.AudioConfig(filename="test.wav")

recognizer = speechsdk.SpeechRecognizer(
    speech_config=speech_config,
    audio_config=audio_config
)

print("🎧 Transcribing...")

result = recognizer.recognize_once()

if result.reason == speechsdk.ResultReason.RecognizedSpeech:
    print("✅ Recognized text:")
    print(result.text)

elif result.reason == speechsdk.ResultReason.NoMatch:
    print("❌ No speech recognized")

elif result.reason == speechsdk.ResultReason.Canceled:
    print("❌ Canceled:", result.cancellation_details.reason)
    print("Details:", result.cancellation_details.error_details)
