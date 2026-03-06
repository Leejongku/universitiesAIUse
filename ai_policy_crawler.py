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
                    href = a["href"].strip()
                    if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                        continue
                        
                    text = a.get_text(separator=" ", strip=True)
                    text_lower = text.lower()

                    is_match = False
                    for k in POLICY_KEYWORDS:
                        if k in text_lower:
                            is_match = True
                            break

                    if is_match:
                        from urllib.parse import urljoin
                        full_url = urljoin(url, href)
                        display_title = text if text else href
                        
                        results.append(
                            {
                                "university": uni["name"],
                                "title": display_title,
                                "url": full_url,
                            }
                        )

            except Exception:
                pass

        return results