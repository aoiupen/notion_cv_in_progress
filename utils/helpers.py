import os
import re
import requests
from bs4 import BeautifulSoup

def get_styles():
    """루트(최상위) 경로의 portfolio_style.css 파일 내용을 반환합니다."""
    css_path = os.path.join(os.getcwd(), 'portfolio_style.css')
    try:
        with open(css_path, encoding='utf-8') as f:
            css = f.read()
        return css
    except Exception as e:
        print(f"CSS 파일 읽기 오류: {e}")
        # 백업용 기본 CSS 반환
        return """
        @page { size: A4; margin: 2cm; }
        body { font-family: 'Pretendard', sans-serif; line-height: 1.6; color: #333; }
        h1 { font-size: 2.5em; margin: 1.2em 0 0.1em 0; }
        h2 { font-size: 1.8em; margin: 1.1em 0 0.4em 0; }
        h3 { font-size: 1.2em; margin: 0.9em 0 0.3em 0; }
        """

def extract_page_title(page_info, default_if_empty=False):
    """Notion 페이지 정보에서 제목을 추출합니다."""
    try:
        properties = page_info.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                title_array = prop_data.get('title', [])
                if title_array:
                    plain_text = ''.join([item['plain_text'] for item in title_array]).strip()
                    if plain_text:
                        return plain_text
        
        return "새 페이지" if default_if_empty else ""
    except Exception as e:
        print(f"제목 추출 중 오류: {e}")
        return "새 페이지" if default_if_empty else ""

def is_youtube_url(url):
    return (
        url.startswith("https://www.youtube.com/") or
        url.startswith("https://youtu.be/")
    )

def get_youtube_info(url):
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    try:
        resp = requests.get(oembed_url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "title": data.get("title", "YouTube Video"),
                "favicon": "https://www.youtube.com/favicon.ico"
            }
    except Exception:
        pass
    return {
        "title": "YouTube Video",
        "favicon": "https://www.youtube.com/favicon.ico"
    }

def is_github_url(url):
    return url.startswith("https://github.com/")

def clean_github_title(title):
    title = re.sub(r'[-·]\s*GitHub.*$', '', title).strip()
    if ' - ' in title:
        parts = title.split(' - ')
        return parts[-1].strip()
    return title.strip()

def get_github_info(url):
    match = re.search(r'github\.com/([^/]+)/([^/?#]+)', url)
    if match:
        owner, repo = match.group(1), match.group(2)
        api_url = f'https://api.github.com/repos/{owner}/{repo}'
        try:
            resp = requests.get(api_url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "title": data.get("name", f"{owner}/{repo}"),
                    "favicon": "https://github.com/fluidicon.png"
                }
        except Exception:
            pass
        return {
            "title": repo,
            "favicon": "https://github.com/fluidicon.png"
        }
    try:
        resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else "GitHub"
            title = clean_github_title(title)
            return {
                "title": title,
                "favicon": "https://github.com/fluidicon.png"
            }
    except Exception:
        pass
    return {
        "title": "GitHub",
        "favicon": "https://github.com/fluidicon.png"
    }

def is_gmail_url(url):
    return url.startswith("mailto:") and ("@gmail.com" in url or "@googlemail.com" in url)

def get_gmail_info(url):
    return {
        "title": url.replace("mailto:", ""),
        "favicon": "https://ssl.gstatic.com/ui/v1/icons/mail/rfr/gmail.ico"
    }

def is_linkedin_url(url):
    return url.startswith("https://www.linkedin.com/") or url.startswith("http://www.linkedin.com/")

def get_linkedin_info(url):
    title_match = re.search(r'linkedin\.com/in/([^/?#]+)', url)
    if title_match:
        profile_name = title_match.group(1).replace('-', ' ').title()
        title = f"{profile_name}'s LinkedIn"
    else:
        title = "LinkedIn Profile"
    return {
        "title": title
    } 