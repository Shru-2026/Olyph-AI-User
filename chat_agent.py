# chat_agent.py
"""
Ask-me-anything agent for Olyph AI.

- Loads FAQ from a Google Sheet (preferred) or falls back to PDF.
- Uses TF-IDF similarity to answer from FAQ; if weak, falls back to Azure OpenAI chat.
"""

import os
import re
import fitz
import nltk
import traceback
import math
from pathlib import Path
from dotenv import load_dotenv

# sklearn & text utils
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Google Sheets
import json
import gspread
from google.oauth2.service_account import Credentials

# Azure/OpenAI (same SDK usage as before)
from openai import AzureOpenAI

load_dotenv()
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

# ---------- CONFIG ----------
FAQ_FROM_SHEET_ID = os.getenv("CHAT_FAQ_SHEET_ID", "").strip()
FAQ_FROM_SHEET_NAME = os.getenv("CHAT_FAQ_SHEET_NAME", "FAQ").strip()
FAQ_PDF_PATH = os.getenv("CHAT_FAQ_PDF_PATH", "Olyphaunt FAQs.pdf")
threshold = float(os.getenv("CHAT_FAQ_SIM_THRESHOLD", 0.6))

DEBUG = os.getenv("CHAT_DEBUG", "") not in ("", "0", "false", "False")

# ---------- Azure/OpenAI config ----------
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT):
    print("⚠️ Warning: Azure OpenAI config missing in environment. Chat fallback may be limited.")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ---------- Google creds helper (copied pattern used in survey_agent) ----------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_google_creds():
    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if json_content:
        try:
            info = json.loads(json_content)
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_path and os.path.exists(json_path):
        return Credentials.from_service_account_file(json_path, scopes=SCOPES)

    render_path = "/etc/secrets/service_account.json"
    if os.path.exists(render_path):
        return Credentials.from_service_account_file(render_path, scopes=SCOPES)

    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    # No creds found
    return None

def load_faq_from_sheet():
    """
    Attempt to read FAQ from a Google Sheet.
    Expects a worksheet with columns containing 'Question' and 'Answer' (case-insensitive).
    Returns list of (question, answer) pairs or [] on error/empty.
    """
    if not FAQ_FROM_SHEET_ID:
        if DEBUG:
            print("[FAQ] No CHAT_FAQ_SHEET_ID configured; skipping sheet load.")
        return []

    creds = get_google_creds()
    if creds is None:
        if DEBUG:
            print("[FAQ] Google credentials not found; cannot load FAQ sheet.")
        return []

    try:
        gc = gspread.authorize(creds)
        wb = gc.open_by_key(FAQ_FROM_SHEET_ID)
        ws = wb.worksheet(FAQ_FROM_SHEET_NAME)
        rows = ws.get_all_records()
        if not rows:
            if DEBUG:
                print(f"[FAQ] Sheet '{FAQ_FROM_SHEET_NAME}' is empty.")
            return []

        # find header keys for question and answer (case-insensitive)
        headers = [h.strip() for h in ws.row_values(1)]
        # find column names matching common variants
        def find_col(names):
            for n in headers:
                ln = n.strip().lower()
                if ln in names:
                    return n  # return exact header text
            return None

        qcol = find_col({"question", "q", "prompt", "query", "formquestion"})
        acol = find_col({"answer", "response", "modelanswer", "reply"})
        if not qcol or not acol:
            # try tolerant matching by substring
            for h in headers:
                hl = h.lower()
                if not qcol and ("question" in hl or "q " in hl or hl.endswith("?")):
                    qcol = h
                if not acol and ("answer" in hl or "response" in hl):
                    acol = h

        if not qcol or not acol:
            raise ValueError(f"Could not detect Question/Answer columns in sheet headers: {headers}")

        qa_pairs = []
        for r in rows:
            q = (r.get(qcol) or "").strip()
            a = (r.get(acol) or "").strip()
            if q and a:
                qa_pairs.append((q, a))
        if DEBUG:
            print(f"[FAQ] Loaded {len(qa_pairs)} Q/A pairs from sheet '{FAQ_FROM_SHEET_NAME}'.")
        return qa_pairs

    except Exception as e:
        if DEBUG:
            print("[FAQ] Error loading FAQ sheet:", type(e).__name__, e)
            traceback.print_exc()
        return []

# ---------- PDF FAQ loader (fallback) ----------
def extract_pdf_text(pdf_path: str):
    qa_pairs = []
    try:
        if not os.path.exists(pdf_path):
            if DEBUG:
                print(f"[FAQ] PDF not found at '{pdf_path}'")
            return []
        with fitz.open(pdf_path) as doc:
            text = ""
            for p in range(len(doc)):
                text += doc[p].get_text("text")

        lines = text.splitlines()
        question, answer = None, ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Question line (heuristic)
            if re.match(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", line.lower()) or line.endswith("?"):
                if question and answer:
                    qa_pairs.append((question.strip(), answer.strip()))
                question = re.sub(
                    r"^(q\d*[\.\):]*|question[\.\):]*|q:)",
                    "",
                    line,
                    flags=re.I,
                ).strip()
                answer = ""
            elif re.match(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", line.lower()):
                answer_line = re.sub(
                    r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)",
                    "",
                    line,
                    flags=re.I,
                ).strip()
                answer += " " + answer_line
            elif question:
                answer += " " + line

        if question and answer:
            qa_pairs.append((question.strip(), answer.strip()))

        if DEBUG:
            print(f"[FAQ] Extracted {len(qa_pairs)} Q/A pairs from PDF '{pdf_path}'")
        return qa_pairs

    except Exception as e:
        if DEBUG:
            print(f"[FAQ] Error reading PDF '{pdf_path}': {type(e).__name__}: {e}")
            traceback.print_exc()
        return []

# ---------- Load QA (sheet preferred, then pdf fallback) ----------
qa_pairs = []
qa_pairs = load_faq_from_sheet()
if not qa_pairs:
    if DEBUG:
        print("[FAQ] Falling back to PDF loader.")
    qa_pairs = extract_pdf_text(FAQ_PDF_PATH)

if not qa_pairs:
    # final tiny fallback so chat still works
    qa_pairs = [
        ("What is Olyphaunt Solutions?", "Olyphaunt Solutions is a healthcare technology company.")
    ]
    if DEBUG:
        print("[FAQ] Using default fallback QA pair.")

# ---------- Chatbot class (same logic, but uses loaded qa_pairs) ----------
class OlyphauntChatbot:
    def __init__(self, qa_pairs):
        self.qa_pairs = qa_pairs
        self.questions = [q.lower() for q, _ in qa_pairs]
        self.answers = [a for _, a in qa_pairs]
        sw = stopwords.words("english")
        self.vectorizer = TfidfVectorizer(stop_words=sw)
        try:
            self.question_vectors = self.vectorizer.fit_transform(self.questions)
        except Exception as e:
            if DEBUG:
                print("⚠️ Vectorizer fit failed:", e)
                traceback.print_exc()
            self.question_vectors = None

    def _extract_text_from_choice(self, choice):
        try:
            if hasattr(choice, "message"):
                msg = choice.message
                if isinstance(msg, dict) and "content" in msg:
                    return msg.get("content")
                if hasattr(msg, "content"):
                    return msg.content
        except Exception:
            pass
        try:
            if isinstance(choice, dict) and "message" in choice and isinstance(choice["message"], dict):
                return choice["message"].get("content")
        except Exception:
            pass
        try:
            if hasattr(choice, "text"):
                return choice.text
        except Exception:
            pass
        return None

    def respond(self, user_query: str) -> str:
        user_query_text = (user_query or "").strip()
        if not user_query_text:
            return "⚠️ Please enter a valid question."

        # 1) FAQ via TF-IDF similarity
        try:
            if self.question_vectors is not None:
                qvec = self.vectorizer.transform([user_query_text.lower()])
                sims = cosine_similarity(qvec, self.question_vectors)
                max_idx = int(sims.argmax())
                score = float(sims[0, max_idx])
                if DEBUG:
                    print(f"[FAQ] similarity score: {score:.3f} (threshold {threshold}) -> idx {max_idx}")
                if score >= threshold:
                    return self.answers[max_idx]
        except Exception as e:
            if DEBUG:
                print("[FAQ] check error:", type(e).__name__, e)
                traceback.print_exc()

        # 2) Fallback: Azure OpenAI
        try:
            if DEBUG:
                print("[AZURE] Calling Azure chat fallback...")
            messages = [
                {"role": "system", "content": "You are an assistant for Olyphaunt Solutions."},
                {"role": "user", "content": user_query_text},
            ]
            resp = client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.2,
                max_tokens=256,
            )
            if DEBUG:
                print("[AZURE] raw resp:", resp)
            if hasattr(resp, "choices") and len(resp.choices) > 0:
                choice0 = resp.choices[0]
                text = self._extract_text_from_choice(choice0)
                if text:
                    return text.strip()
            return "🤖 I'm not certain about that. Could you rephrase or provide more details?"
        except Exception as e:
            if DEBUG:
                print(f"[AZURE] error: {type(e).__name__}: {e}")
                traceback.print_exc()
            return "⚠️ Olyph AI is currently offline or Azure OpenAI returned an error. Please try again later."

# single global instance
chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str) -> str:
    """
    Public function used by Flask route /ask.
    """
    return chatbot.respond(user_message)
