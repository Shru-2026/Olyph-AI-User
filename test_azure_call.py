# test_azure_call.py
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv("./.env")

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

print("endpoint:", AZURE_OPENAI_ENDPOINT)
print("deployment:", AZURE_DEPLOYMENT_NAME)
print("api_version:", AZURE_API_VERSION)

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Say hello and tell me your model name."}
]

try:
    resp = client.chat.completions.create(
        model=AZURE_DEPLOYMENT_NAME,
        messages=messages,
        max_tokens=200
    )
    print("RAW RESPONSE:", resp)
    # Try common extraction patterns:
    try:
        if hasattr(resp, "choices") and len(resp.choices) > 0:
            c0 = resp.choices[0]
            # Try several paths
            if isinstance(c0, dict) and "message" in c0:
                print("content:", c0["message"].get("content"))
            elif hasattr(c0, "message") and isinstance(c0.message, dict):
                print("content:", c0.message.get("content"))
            elif hasattr(c0, "text"):
                print("content:", c0.text)
            else:
                print("Could not parse choice0:", c0)
    except Exception as ex:
        print("Parsing error:", ex)
except Exception as e:
    print("ERROR calling Azure:", type(e).__name__, e)

