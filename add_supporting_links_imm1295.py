import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

TARGET_PAGE = "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1295.html"
SOURCES_FILE = "sources.txt"

# We keep links likely to contain instructions/checklists/guidance
KEEP_PATTERNS = [
    r"/services/application/application-forms-guides/guide-",
    r"/services/application/application-forms-guides/imm\d+\.html",
    r"/content/dam/ircc/.*\.pdf",
]

# We explicitly ignore the XFA form PDF (not useful for text RAG)
DROP_EXACT = {
    "https://www.canada.ca/content/dam/ircc/documents/pdf/english/kits/forms/imm1295/01-09-2023/imm1295e.pdf"
}

def main():
    r = requests.get(TARGET_PAGE, timeout=30, headers={"User-Agent": "ircc-rag-bot/0.1"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(TARGET_PAGE, href).split("#")[0]

        if "canada.ca" not in full:
            continue
        if full in DROP_EXACT:
            continue

        if any(re.search(p, full, re.IGNORECASE) for p in KEEP_PATTERNS):
            links.add(full)

    if not links:
        print("No supporting links found.")
        return

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        existing = set(line.strip() for line in f if line.strip())

    new_links = [u for u in sorted(links) if u not in existing]

    if not new_links:
        print("All supporting links already exist in sources.txt")
        return

    with open(SOURCES_FILE, "a", encoding="utf-8") as f:
        for u in new_links:
            f.write("\n" + u)

    print(f"Added {len(new_links)} supporting URLs to sources.txt:")
    for u in new_links:
        print("  " + u)

if __name__ == "__main__":
    main()
