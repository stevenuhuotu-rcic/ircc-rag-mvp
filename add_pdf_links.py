import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

TARGET_PAGE = "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1295.html"
SOURCES_FILE = "sources.txt"

def main():
    r = requests.get(TARGET_PAGE, timeout=30, headers={"User-Agent": "ircc-rag-bot/0.1"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    pdfs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(TARGET_PAGE, href).split("#")[0]
        if full.lower().endswith(".pdf") and "canada.ca" in full:
            pdfs.add(full)

    if not pdfs:
        print("No PDF links found on IMM1295 page.")
        return

    # Read existing sources to avoid duplicates
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        existing = set(line.strip() for line in f if line.strip())

    new_pdfs = [p for p in sorted(pdfs) if p not in existing]

    if not new_pdfs:
        print(f"Found {len(pdfs)} PDF links, but all are already in {SOURCES_FILE}.")
        return

    with open(SOURCES_FILE, "a", encoding="utf-8") as f:
        for p in new_pdfs:
            f.write("\n" + p)

    print(f"Added {len(new_pdfs)} new PDF URLs to {SOURCES_FILE}:")
    for p in new_pdfs:
        print("  " + p)

if __name__ == "__main__":
    main()
