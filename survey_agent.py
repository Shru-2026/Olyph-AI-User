# survey_agent_debug.py
# (updated to load question bank from a sheet – Render ready)

import os
import json
import math
import gspread
from google.oauth2.service_account import Credentials
from openai import AzureOpenAI
from dotenv import load_dotenv
import traceback
from collections import Counter

# -------------------------------------------------
# Load .env explicitly (Render Secret Files support)
# -------------------------------------------------
ENV_PATH = "/etc/secrets/.env"

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
else:
    load_dotenv()  # local development fallback

# -----------------------
# CONFIG / ENV
# -----------------------
DEBUG = os.getenv("SURVEY_DEBUG", "") not in ("", "0", "false", "False")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -----------------------
# GOOGLE SHEETS AUTH
# -----------------------
def get_google_creds():
    """
    Priority:
    1) GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT (optional)
    2) Render Secret File: /etc/secrets/service_account.json
    3) Local fallback: ./creds/service_account.json
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

    raise FileNotFoundError("No Google credentials found for survey agent!")

creds = get_google_creds()
gc = gspread.authorize(creds)
if DEBUG:
    print("[SURVEY][DEBUG] Google Sheets client authorized.")

# -----------------------
# SPREADSHEET CONFIG (env)
# -----------------------
SPREADSHEET_ID = os.getenv(
    "SURVEY_SHEET_ID",
    "17bCNu8teY-KM5154YVA1_90xLKBlMrLAKkjy0AVJK1w"
)
RESPONSES_SHEET_NAME = os.getenv(
    "SURVEY_RESPONSES_SHEET_NAME",
    "Form Responses 1"
)
QUESTIONBANK_SHEET_NAME = os.getenv(
    "SURVEY_QUESTIONBANK_SHEET_NAME",
    "QuestionBank"
)

# -----------------------
# DYNAMIC QUESTION BANK LOADING
# -----------------------
QUESTION_COLUMNS = {}
MODEL_ANSWERS = {}

def load_question_bank():
    """
    Loads question bank from QUESTIONBANK_SHEET_NAME.
    Expected columns (case-insensitive):
      - QID (optional)
      - FormQuestion (exact header in responses sheet)
      - ModelAnswer
    """
    global QUESTION_COLUMNS, MODEL_ANSWERS
    QUESTION_COLUMNS = {}
    MODEL_ANSWERS = {}

    try:
        wb = gc.open_by_key(SPREADSHEET_ID)
        if DEBUG:
            print("[SURVEY][DEBUG] Worksheets:", [ws.title for ws in wb.worksheets()])
        qb_ws = wb.worksheet(QUESTIONBANK_SHEET_NAME)
    except Exception as e:
        raise RuntimeError(
            f"Unable to open question bank worksheet '{QUESTIONBANK_SHEET_NAME}': {e}"
        )

    rows = qb_ws.get_all_records()
    if not rows:
        raise ValueError(f"Question bank '{QUESTIONBANK_SHEET_NAME}' is empty.")

    def find_key(possible_names):
        for header in qb_ws.row_values(1):
            if header.strip().lower() in possible_names:
                return header
        return None

    qid_col = find_key({"qid", "id", "key"})
    formq_col = find_key({"formquestion", "question", "prompt", "form question"})
    model_col = find_key({"modelanswer", "answer", "model answer", "model_answer"})

    if not formq_col or not model_col:
        raise ValueError(
            "Question bank must contain FormQuestion and ModelAnswer columns."
        )

    auto_counter = 1
    for row in rows:
        formq = (row.get(formq_col) or "").strip()
        model = (row.get(model_col) or "").strip()

        if not formq:
            continue

        if qid_col and row.get(qid_col):
            qid = str(row.get(qid_col)).strip()
        else:
            qid = f"Q{auto_counter}"

        QUESTION_COLUMNS[qid] = formq
        MODEL_ANSWERS[qid] = model
        auto_counter += 1

    if not QUESTION_COLUMNS:
        raise ValueError("No valid questions loaded from question bank.")

    if DEBUG:
        print("[SURVEY][DEBUG] Loaded questions:", QUESTION_COLUMNS)

# Load question bank at import
load_question_bank()

# -----------------------
# AZURE OPENAI SETUP
# -----------------------
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("AZURE_EMBEDDINGS_DEPLOYMENT_NAME")

if not AZURE_ENDPOINT or not AZURE_API_KEY:
    raise RuntimeError("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_KEY not set!")

azure_client = AzureOpenAI(
    api_key=AZURE_API_KEY,
    api_version="2024-02-15-preview",
    azure_endpoint=AZURE_ENDPOINT
)

if DEBUG:
    print("[SURVEY][DEBUG] Azure OpenAI client initialized.")

# -----------------------
# EMBEDDING + SCORING LOGIC
# -----------------------
def simple_bow_embedding(a_text: str, b_text: str):
    def tokenize(s):
        return [t.lower() for t in s.split()] if s else []

    a_tokens = tokenize(a_text)
    b_tokens = tokenize(b_text)
    vocab = list(dict.fromkeys(a_tokens + b_tokens))

    a_counts = Counter(a_tokens)
    b_counts = Counter(b_tokens)

    a_vec = [float(a_counts.get(w, 0)) for w in vocab]
    b_vec = [float(b_counts.get(w, 0)) for w in vocab]

    def normalize(v):
        norm = math.sqrt(sum(x * x for x in v))
        return v if norm == 0 else [x / norm for x in v]

    return normalize(a_vec), normalize(b_vec)

def get_embedding_safe(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        resp = azure_client.embeddings.create(
            model=AZURE_EMBEDDINGS_DEPLOYMENT_NAME,
            input=text
        )
        return [float(x) for x in resp.data[0].embedding]
    except Exception:
        if DEBUG:
            traceback.print_exc()
        return None

def cosine_similarity(vec1, vec2):
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    return 0.0 if n1 == 0 or n2 == 0 else dot / (n1 * n2)

def score_single_pair(model_answer, user_answer):
    model_vec = get_embedding_safe(model_answer)
    user_vec = get_embedding_safe(user_answer)

    if model_vec and user_vec:
        sim = cosine_similarity(model_vec, user_vec)
    else:
        model_vec, user_vec = simple_bow_embedding(model_answer, user_answer)
        sim = cosine_similarity(model_vec, user_vec)

    return round(max(0.0, sim), 1)

def score_answers_with_azure(user_answers: dict):
    scores = {}
    total = 0.0

    for qid, model_answer in MODEL_ANSWERS.items():
        user_answer = (user_answers.get(qid) or "").strip()
        s = score_single_pair(model_answer, user_answer) if user_answer else 0.0
        scores[qid] = s
        total += s

    scores["total"] = round(total, 1)
    return scores

# -----------------------
# PROCESS RESPONSES SHEET
# -----------------------
def process_unscored_responses():
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(RESPONSES_SHEET_NAME)
    header = ws.row_values(1)
    col_index = {h: i + 1 for i, h in enumerate(header)}

    required_scores = [f"Score {qid}" for qid in QUESTION_COLUMNS]
    required = list(QUESTION_COLUMNS.values()) + required_scores + ["Total"]
    missing = [c for c in required if c not in col_index]

    if missing:
        raise ValueError(f"Missing columns in responses sheet: {missing}")

    rows = ws.get_all_records()
    updated = 0

    for i, row in enumerate(rows, start=2):
        first_qid = next(iter(QUESTION_COLUMNS))
        if str(row.get(f"Score {first_qid}", "")).strip():
            continue

        answers = {
            qid: row.get(header_name, "")
            for qid, header_name in QUESTION_COLUMNS.items()
        }

        scores = score_answers_with_azure(answers)

        for qid in QUESTION_COLUMNS:
            ws.update_cell(i, col_index[f"Score {qid}"], scores[qid])
        ws.update_cell(i, col_index["Total"], scores["total"])

        updated += 1

    return f"Updated {updated} responses"

if __name__ == "__main__":
    process_unscored_responses()
