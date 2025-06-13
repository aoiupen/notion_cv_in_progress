import requests
from config import CLAUDE_API_KEY

def translate(text):
    url = "https://api.anthropic.com/v1/complete"
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "content-type": "application/json"
    }
    data = {
        "prompt": f"Translate the following Korean text to English:\n{text}",
        "model": "claude-sonnet-4-202500514",
        "max_tokens_to_sample": 512
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json() 