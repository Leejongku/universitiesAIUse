import requests
from bs4 import BeautifulSoup

AI_KEYWORDS = [
    "gpt",
    "chatbot",
    "ai",
    "챗봇",
    "생성형",
]


class AIServiceCrawler:

    def __init__(self, universities):
        self.universities = universities

    def crawl(self):

        results = []

        for uni in self.universities:

            domain = uni["domain"]

            url = f"https://{domain}"

            try:

                res = requests.get(url, timeout=10)

                soup = BeautifulSoup(res.text, "html.parser")

                for a in soup.find_all("a", href=True):

                    href = a["href"].lower()

                    for k in AI_KEYWORDS:

                        if k in href:

                            results.append(
                                {
                                    "university": uni["name"],
                                    "title": href,
                                    "url": href,
                                }
                            )

            except Exception:
                pass

        return results
        