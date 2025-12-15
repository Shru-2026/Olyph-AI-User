# survey_agent_debug.py (updated to load question bank from a sheet)
import os
import json
import math
import gspread
from google.oauth2.service_account import Credentials
from openai import AzureOpenAI
from dotenv import load_dotenv
import traceback
from collections import Counter

load_dotenv()

# -----------------------
# CONFIG / ENV
# -----------------------
DEBUG = os.getenv("SURVEY_DEBUG", "") not in ("", "0", "false", "False")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -----------------------
# GOOGLE SHEETS AUTH
# -----------------------
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

    raise FileNotFoundError("No Google credentials found for survey agent!")

creds = get_google_creds()
gc = gspread.authorize(creds)
if DEBUG:
    print("[SURVEY][DEBUG] Google Sheets client authorized.")

# -----------------------
# SPREADSHEET CONFIG (env)
# -----------------------
SPREADSHEET_ID = os.getenv("SURVEY_SHEET_ID", "17bCNu8teY-KM5154YVA1_90xLKBlMrLAKkjy0AVJK1w")
RESPONSES_SHEET_NAME = os.getenv("SURVEY_RESPONSES_SHEET_NAME", "Form Responses 1")
QUESTIONBANK_SHEET_NAME = os.getenv("SURVEY_QUESTIONBANK_SHEET_NAME", "QuestionBank")

# -----------------------
# DYNAMIC QUESTION BANK LOADING
# -----------------------
# After calling load_question_bank(), the following two dicts will be set:
#   QUESTION_COLUMNS: dict mapping QID -> FormQuestion (the exact header text in responses sheet)
#   MODEL_ANSWERS: dict mapping QID -> model_answer_text
QUESTION_COLUMNS = {}
MODEL_ANSWERS = {}

def load_question_bank():
    """
    Loads question bank from the QUESTIONBANK_SHEET_NAME worksheet in the spreadsheet.
    Expected columns (case-insensitive): QID, FormQuestion (exact header in responses sheet), ModelAnswer
    If QID is missing, Q1..Qn are generated in row order.
    """
    global QUESTION_COLUMNS, MODEL_ANSWERS
    QUESTION_COLUMNS = {}
    MODEL_ANSWERS = {}

    try:
        wb = gc.open_by_key(SPREADSHEET_ID)
        wb_worksheets = [ws.title for ws in wb.worksheets()]
        if DEBUG:
            print("[SURVEY][DEBUG] Workbooks worksheets:", wb_worksheets)

        # open question bank worksheet
        qb_ws = wb.worksheet(QUESTIONBANK_SHEET_NAME)
    except Exception as e:
        raise RuntimeError(f"Unable to open question bank worksheet '{QUESTIONBANK_SHEET_NAME}': {e}")

    rows = qb_ws.get_all_records()
    if not rows:
        raise ValueError(f"Question bank '{QUESTIONBANK_SHEET_NAME}' is empty or not in expected format.")

    # Normalize keys (first row dict keys)
    first_row_keys = [k.strip().lower() for k in qb_ws.row_values(1)]
    # Determine column names by probing keys from first row mappings
    # Acceptable column names (case-insensitive): qid, id, key ; formquestion, question, prompt ; modelanswer, answer
    def find_key(possible_names):
        for p in possible_names:
            for actual in qb_ws.row_values(1):
                if actual.strip().lower() == p:
                    return actual  # return exact header name as in sheet
        return None

    qid_col = find_key(["qid", "id", "key"])
    formq_col = find_key(["formquestion", "question", "prompt", "form question"])
    model_col = find_key(["modelanswer", "answer", "model answer", "model_answer"])

    if not formq_col or not model_col:
        raise ValueError("Question bank must contain at least columns for FormQuestion and ModelAnswer. "
                         f"Found columns: {qb_ws.row_values(1)}")

    # Build maps
    auto_counter = 1
    for row in rows:
        # row keys are the header strings as in sheet
        # pick values robustly
        formq = row.get(formq_col, "") if formq_col in row else row.get(formq_col.strip(), "")
        model = row.get(model_col, "") if model_col in row else row.get(model_col.strip(), "")

        if isinstance(formq, str):
            formq = formq.strip()
        if isinstance(model, str):
            model = model.strip()

        if not formq:
            # skip rows without a FormQuestion
            continue

        if qid_col:
            qid_val = row.get(qid_col, "")
            if isinstance(qid_val, str) and qid_val.strip():
                qid = qid_val.strip()
            else:
                qid = f"Q{auto_counter}"
        else:
            qid = f"Q{auto_counter}"

        QUESTION_COLUMNS[qid] = formq
        MODEL_ANSWERS[qid] = model
        auto_counter += 1

    if DEBUG:
        print("[SURVEY][DEBUG] Loaded question bank entries:", len(QUESTION_COLUMNS))
        for k in QUESTION_COLUMNS:
            print(f"  {k} -> '{QUESTION_COLUMNS[k]}' (model len={len(MODEL_ANSWERS.get(k,''))})")

    if not QUESTION_COLUMNS:
        raise ValueError("No valid questions loaded from question bank.")

# Load at import time (so the rest of code can use it)
load_question_bank()

# -----------------------
# AZURE OPENAI SETUP
# -----------------------
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("AZURE_EMBEDDINGS_DEPLOYMENT_NAME")

if not AZURE_ENDPOINT or not AZURE_API_KEY:
    raise RuntimeError("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_KEY not set!")

azure_client = AzureOpenAI(api_key=AZURE_API_KEY, api_version="2024-02-15-preview", azure_endpoint=AZURE_ENDPOINT)
if DEBUG:
    print("[SURVEY][DEBUG] Azure OpenAI client initialized.")


# -----------------------
# (rest of your code stays the same: fallback embedding, get_embedding_safe, cosine_similarity, scoring)
# Copy the functions simple_bow_embedding, get_embedding_safe, cosine_similarity, score_single_pair, score_answers_with_azure unchanged
# -----------------------

# (I will re-include them below exactly as you previously had them to make this file self-contained)
def simple_bow_embedding(a_text: str, b_text: str):
    def tokenize(s):
        if not s:
            return []
        return [tok.lower() for tok in s.split()]

    a_tokens = tokenize(a_text)
    b_tokens = tokenize(b_text)
    vocab = list(dict.fromkeys(a_tokens + b_tokens))
    a_counts = Counter(a_tokens)
    b_counts = Counter(b_tokens)
    a_vec = [float(a_counts.get(w, 0)) for w in vocab]
    b_vec = [float(b_counts.get(w, 0)) for w in vocab]

    def normalize(v):
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            return v
        return [x / norm for x in v]
    return normalize(a_vec), normalize(b_vec)


def get_embedding_safe(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        resp = azure_client.embeddings.create(model=AZURE_EMBEDDINGS_DEPLOYMENT_NAME, input=text)
        embedding = None
        if hasattr(resp, "data") and isinstance(resp.data, list) and len(resp.data) > 0:
            item = resp.data[0]
            if hasattr(item, "embedding"):
                embedding = item.embedding
            elif isinstance(item, dict) and "embedding" in item:
                embedding = item["embedding"]
        if embedding is None:
            if DEBUG:
                print("[SURVEY][DEBUG] Azure embedding returned unexpected structure. Using fallback.")
            return None
        embedding = [float(x) for x in embedding]
        return embedding
    except Exception as e:
        if DEBUG:
            print("[SURVEY][DEBUG] Azure embedding call failed:", e)
            traceback.print_exc()
        return None


def cosine_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0
    if len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def score_single_pair(model_answer: str, user_answer: str):
    model_vec = get_embedding_safe(model_answer)
    user_vec = get_embedding_safe(user_answer) if user_answer else None

    if model_vec is not None and user_vec is not None:
        if DEBUG:
            print(f"[SURVEY][DEBUG] Using Azure embeddings: len={len(model_vec)}")
            print("  sample model_vec[:5]:", model_vec[:5])
            print("  sample user_vec[:5]: ", user_vec[:5])
    else:
        if DEBUG:
            print("[SURVEY][DEBUG] Using fallback bag-of-words embeddings.")
        model_vec, user_vec = simple_bow_embedding(model_answer, user_answer or "")

    raw_sim = cosine_similarity(model_vec, user_vec)
    mapped = max(0.0, raw_sim)
    final = round(mapped, 1)
    if DEBUG:
        print(f"[SURVEY][DEBUG] raw_sim={raw_sim:.6f} mapped={mapped:.6f} final={final}")
    return final


def score_answers_with_azure(user_answers: dict) -> dict:
    scores = {}
    total = 0.0
    for qid, model_answer in MODEL_ANSWERS.items():
        user_answer = (user_answers.get(qid) or "").strip()
        if not user_answer:
            scores[qid] = 0.0
        else:
            try:
                s = score_single_pair(model_answer, user_answer)
                scores[qid] = s
                total += s
            except Exception as e:
                if DEBUG:
                    print(f"[SURVEY][DEBUG] Error scoring {qid}:", e)
                    traceback.print_exc()
                scores[qid] = 0.0
    scores["total"] = round(total, 1)
    if DEBUG:
        print("[SURVEY][DEBUG] Scored answers:", scores)
    return scores

# -----------------------
# PROCESS SHEET (uses dynamic QUESTION_COLUMNS / MODEL_ANSWERS)
# -----------------------
def process_unscored_responses():
    if DEBUG:
        print("[SURVEY][DEBUG] Starting processing...")

    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(RESPONSES_SHEET_NAME)
    header = ws.row_values(1)
    col_index = {name: idx + 1 for idx, name in enumerate(header)}

    # Build required columns list dynamically:
    # For each QID we expect a Score column named "Score <QID>" (same format you used earlier)
    required_score_cols = [f"Score {qid}" for qid in QUESTION_COLUMNS.keys()]
    required = list(QUESTION_COLUMNS.values()) + required_score_cols + ["Total"]
    missing = [c for c in required if c not in col_index]
    if missing:
        raise ValueError(f"Missing required column(s) in responses sheet: {missing}. "
                         "Ensure question headers match FormQuestion entries in question bank, "
                         "and Score columns exist (e.g. 'Score Q1').")

    rows = ws.get_all_records()
    if DEBUG:
        print(f"[SURVEY][DEBUG] Rows fetched: {len(rows)}")

    updated = 0
    for i, row in enumerate(rows, start=2):
        # treat any non-empty first Score column as already scored (we check Q1 if exists)
        first_qid = next(iter(QUESTION_COLUMNS.keys()))
        first_score_col = f"Score {first_qid}"
        if str(row.get(first_score_col, "")).strip() != "":
            continue

        # map responses to QIDs using QUESTION_COLUMNS: QUESTION_COLUMNS[qid] is the exact header name in responses
        answers = {}
        for qid, form_header in QUESTION_COLUMNS.items():
            answers[qid] = row.get(form_header, "")  # may be None -> treat as ""

        if DEBUG:
            print(f"[SURVEY][DEBUG] Row {i} answers:", answers)

        scores = score_answers_with_azure(answers)

        if DEBUG:
            print(f"[SURVEY][DEBUG] Row {i} computed scores:", scores)
        else:
            # write back scores using corresponding "Score <QID>" columns
            for qid in QUESTION_COLUMNS.keys():
                score_col = f"Score {qid}"
                ws.update_cell(i, col_index[score_col], scores.get(qid, 0.0))
            ws.update_cell(i, col_index["Total"], scores.get("total", 0.0))
        updated += 1

    if DEBUG:
        print(f"[SURVEY][DEBUG] Done. Would have updated {updated} rows (DEBUG mode).")
    else:
        print(f"Done. Updated {updated} rows.")
    return f"Updated {updated} responses"

if __name__ == "__main__":
    process_unscored_responses()
