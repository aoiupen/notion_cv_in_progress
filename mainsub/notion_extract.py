from notion_client import Client
from config import NOTION_API_KEY

def extract(page_id):
    notion = Client(auth=NOTION_API_KEY)
    page = notion.pages.retrieve(page_id=page_id)
    return page 