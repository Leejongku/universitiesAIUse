import requests
from bs4 import BeautifulSoup

POLICY_KEYWORDS = [
    "ai 가이드라인",
    "생성형 ai",
    "ai 정책",
]


class AIPolicyCrawler:

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

                    text = a.get_text().lower()

                    for k in POLICY_KEYWORDS:

                        if k in text:

                            results.append(
                                {
                                    "university": uni["name"],
                                    "title": text,
                                    "url": a["href"],
                                }
                            )

            except Exception:
                pass

        return results