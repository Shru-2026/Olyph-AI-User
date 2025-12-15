# app_chat_survey.py
import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Conversational + Survey imports
from chat_agent import handle_user_query
from survey_agent import process_unscored_responses

# NEW: Speech-to-text
from speech_to_text import transcribe_pcm

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)


@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception:
        return """
        <!doctype html><html><head><meta charset="utf-8"><title>Olyph AI</title></head>
        <body><h3>Olyph AI Backend (Chat + Survey)</h3>
        <p>Open the frontend at / (templates/index.html)</p></body></html>
        """


# -----------------------------
# TEXT CHAT (UNCHANGED)
# -----------------------------
@app.route('/ask', methods=['POST'])
def ask():
    try:
        user_input = request.json.get('message', '')
        if not user_input or not user_input.strip():
            return jsonify({'reply': "⚠️ Please enter a valid message."})
        response = handle_user_query(user_input)
        return jsonify({'reply': response})
    except Exception as e:
        print(f"❌ Error in /ask route: {type(e).__name__}: {e}")
        return jsonify({'reply': "⚠️ Something went wrong on the server. Check logs."})


# -----------------------------
# SPEECH → CHAT (NEW)
# -----------------------------
@app.route('/speech-chat', methods=['POST'])
def speech_chat():
    try:
        data = request.get_json()
        pcm_base64 = data.get("audio")
        sample_rate = data.get("sampleRate", 16000)

        if not pcm_base64:
            return jsonify({"reply": "No audio received"})

        import base64
        pcm_bytes = base64.b64decode(pcm_base64)

        transcript = transcribe_pcm(pcm_bytes, sample_rate)

        if not transcript:
            return jsonify({
                "transcript": "",
                "reply": "⚠️ I couldn't understand the audio."
            })

        reply = handle_user_query(transcript)

        return jsonify({
            "transcript": transcript,
            "reply": reply
        })

    except Exception as e:
        print("❌ Speech error:", e)
        return jsonify({"reply": "Speech service error"})



# -----------------------------
# SURVEY (UNCHANGED)
# -----------------------------
@app.route('/api/survey/process', methods=['POST', 'GET'])
def api_survey_process():
    try:
        msg = process_unscored_responses()
        return jsonify({"status": "ok", "message": msg})
    except FileNotFoundError as e:
        print("❌ /api/survey/process FileNotFoundError:", e)
        return jsonify({
            "status": "error",
            "message": "Service account JSON not found. Check SERVICE_ACCOUNT_FILE path."
        }), 500
    except Exception as e:
        print("❌ /api/survey/process error:", type(e).__name__, e)
        return jsonify({
            "status": "error",
            "message": f"Internal error: {type(e).__name__}: {str(e)}"
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
