import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

SEED_FILE = "sources.txt"
OUTPUT_FILE = "sources_expanded.txt"
MAX_LINKS = 75  # safety limit so we don't ingest thousands

def is_valid_ircc_link(url):
    parsed = urlparse(url)
    if "canada.ca" not in parsed.netloc:
        return False
    if "immigration-refugees-citizenship" not in parsed.path:
        return False
    if url.endswith(".pdf"):
        return True
    return True

def extract_links(url):
    print(f"Extracting links from: {url}")
    r = requests.get(url, timeout=30)
    soup = BeautifulSoup(r.text, "lxml")

    links = set()
    for a in soup.find_all("a", href=True):
        full_url = urljoin(url, a["href"])
        if is_valid_ircc_link(full_url):
            links.add(full_url.split("#")[0])

    return links

def main():
    with open(SEED_FILE, "r") as f:
        seeds = [line.strip() for line in f if line.strip()]

    all_links = set(seeds)

    for seed in seeds:
        links = extract_links(seed)
        for link in links:
            if len(all_links) >= MAX_LINKS:
                break
            all_links.add(link)

    print(f"\nTotal links collected: {len(all_links)}")

    with open(OUTPUT_FILE, "w") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
