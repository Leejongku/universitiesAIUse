import csv

from ai_service_crawler import AIServiceCrawler
from ai_policy_crawler import AIPolicyCrawler


universities = []

with open("universities.csv", encoding="utf-8") as f:

    reader = csv.DictReader(f)

    for row in reader:

        universities.append(row)


print("AI 서비스 탐지 시작")

service_crawler = AIServiceCrawler(universities)

services = service_crawler.crawl()

for s in services:

    print(s)


print("\nAI 정책 탐지 시작")

policy_crawler = AIPolicyCrawler(universities)

policies = policy_crawler.crawl()

for p in policies:

    print(p)