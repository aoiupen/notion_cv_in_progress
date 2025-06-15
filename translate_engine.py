import requests
from dataclasses import dataclass
from typing import Optional
from config import CLAUDE_API_KEY

@dataclass
class TranslationConfig:
    source_lang: str
    target_lang: str
    with_translation: bool = True

class TranslateEngine:
    def __init__(self, api_key: str = CLAUDE_API_KEY):
        self.api_key = api_key

    async def translate_content_with_claude(self, text: str, source_lang: str, target_lang: str) -> str:
        if source_lang == target_lang:
            return text
        try:
            headers = {
                "x-api-key": self.api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            prompt = self._create_translation_prompt(text, source_lang, target_lang)
            data = {
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return result["content"][0]["text"]
            else:
                print(f"번역 API 오류: {response.status_code}")
                return text
        except Exception as e:
            print(f"번역 중 오류 발생: {e}")
            return text

    def _create_translation_prompt(self, text: str, source_lang: str, target_lang: str) -> str:
        lang_map = {"ko": "Korean", "en": "English"}
        source = lang_map.get(source_lang, "Korean")
        target = lang_map.get(target_lang, "English")
        return f"""
Please translate the following {source} text to {target}. 
Maintain the professional tone and technical terminology appropriately.
Keep the original formatting and structure.

Text to translate:
{text}

Translation:
"""

    async def translate_and_enhance(self, text: str, config: TranslationConfig) -> Optional[str]:
        if config.with_translation and config.source_lang != config.target_lang:
            return await self.translate_content_with_claude(text, config.source_lang, config.target_lang)
        return text 