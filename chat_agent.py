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

# -------------------------------------------------
# Explicit .env loading (Render Secret Files support)
# -------------------------------------------------
ENV_PATH = "/etc/secrets/.env"

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
else:
    load_dotenv()  # local development fallback

# sklearn & text utils
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Google Sheets
import json
import gspread
from google.oauth2.service_account import Credentials

# Azure OpenAI
from openai import AzureOpenAI

# NLTK resources
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

# ---------- CONFIG ----------
FAQ_FROM_SHEET_ID = os.getenv("CHAT_FAQ_SHEET_ID", "").strip()
FAQ_FROM_SHEET_NAME = os.getenv("CHAT_FAQ_SHEET_NAME", "FAQ").strip()
FAQ_PDF_PATH = os.getenv("CHAT_FAQ_PDF_PATH", "Olyphaunt FAQs.pdf")
threshold = float(os.getenv("CHAT_FAQ_SIM_THRESHOLD", 0.6))

DEBUG = os.getenv("CHAT_DEBUG", "") not in ("", "0", "false", "False")

# ---------- Azure OpenAI config ----------
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT):
    print("⚠️ Warning: Azure OpenAI config missing in environment.")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ---------- Google credentials helper ----------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_google_creds():
    """
    Priority:
    1) GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT (optional)
    2) Render Secret File: /etc/secrets/service_account.json
    3) Local dev fallback: ./creds/service_account.json
    """

    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if json_content:
        try:
            info = json.loads(json_content)
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    render_path = "/etc/secrets/service_account.json"
    if os.path.exists(render_path):
        return Credentials.from_service_account_file(render_path, scopes=SCOPES)

    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    return None

# ---------- Load FAQ from Google Sheet ----------
def load_faq_from_sheet():
    if not FAQ_FROM_SHEET_ID:
        if DEBUG:
            print("[FAQ] CHAT_FAQ_SHEET_ID not set; skipping sheet load.")
        return []

    creds = get_google_creds()
    if creds is None:
        if DEBUG:
            print("[FAQ] Google credentials not found.")
        return []

    try:
        gc = gspread.authorize(creds)
        wb = gc.open_by_key(FAQ_FROM_SHEET_ID)
        ws = wb.worksheet(FAQ_FROM_SHEET_NAME)
        rows = ws.get_all_records()

        if not rows:
            return []

        headers = [h.strip() for h in ws.row_values(1)]

        def find_col(names):
            for h in headers:
                if h.lower() in names:
                    return h
            return None

        qcol = find_col({"question", "q", "prompt", "query", "formquestion"})
        acol = find_col({"answer", "response", "modelanswer", "reply"})

        if not qcol or not acol:
            raise ValueError("Question/Answer columns not found in FAQ sheet")

        qa_pairs = []
        for r in rows:
            q = (r.get(qcol) or "").strip()
            a = (r.get(acol) or "").strip()
            if q and a:
                qa_pairs.append((q, a))

        if DEBUG:
            print(f"[FAQ] Loaded {len(qa_pairs)} Q/A pairs from sheet")

        return qa_pairs

    except Exception as e:
        if DEBUG:
            print("[FAQ] Sheet load error:", e)
            traceback.print_exc()
        return []

# ---------- PDF FAQ fallback ----------
def extract_pdf_text(pdf_path: str):
    qa_pairs = []
    if not os.path.exists(pdf_path):
        return qa_pairs

    try:
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

            if line.endswith("?"):
                if question and answer:
                    qa_pairs.append((question, answer.strip()))
                question = line
                answer = ""
            elif question:
                answer += " " + line

        if question and answer:
            qa_pairs.append((question, answer.strip()))

        return qa_pairs

    except Exception:
        traceback.print_exc()
        return []

# ---------- Load QA ----------
qa_pairs = load_faq_from_sheet()
if not qa_pairs:
    qa_pairs = extract_pdf_text(FAQ_PDF_PATH)

if not qa_pairs:
    qa_pairs = [
        ("What is Olyphaunt Solutions?", "Olyphaunt Solutions is a healthcare technology company.")
    ]

# ---------- Chatbot ----------
class OlyphauntChatbot:
    def __init__(self, qa_pairs):
        self.qa_pairs = qa_pairs
        self.questions = [q.lower() for q, _ in qa_pairs]
        self.answers = [a for _, a in qa_pairs]
        self.vectorizer = TfidfVectorizer(stop_words=stopwords.words("english"))
        try:
            self.question_vectors = self.vectorizer.fit_transform(self.questions)
        except Exception:
            self.question_vectors = None

    def respond(self, user_query: str) -> str:
        if not user_query:
            return "⚠️ Please enter a valid question."

        try:
            if self.question_vectors is not None:
                qvec = self.vectorizer.transform([user_query.lower()])
                sims = cosine_similarity(qvec, self.question_vectors)
                idx = sims.argmax()
                if sims[0, idx] >= threshold:
                    return self.answers[idx]
        except Exception:
            traceback.print_exc()

        # Azure fallback
        try:
            resp = client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are an assistant for Olyphaunt Solutions."},
                    {"role": "user", "content": user_query},
                ],
                temperature=0.2,
                max_tokens=256,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            traceback.print_exc()
            return "⚠️ Azure OpenAI is currently unavailable."

# ---------- Public handler ----------
chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str) -> str:
    return chatbot.respond(user_message)
