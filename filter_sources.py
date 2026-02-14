from urllib.parse import urlparse

INPUT_FILE = "sources_expanded.txt"
OUTPUT_FILE = "sources_filtered.txt"

# Keep: manuals/guidelines + application guides + PDFs
KEEP_CONTAINS = [
    "/operational-bulletins-manuals/",
    "/application-forms-guides/",
    ".pdf",
]

# Drop: pages that are mostly navigation or corporate info
DROP_CONTAINS = [
    "/corporate/contact",
    "/corporate.html",
    "/corporate/",
    "/immigration-refugees-citizenship.html",
    "/fees",
]

# Drop “bulletins by year” index pages (mostly link farms)
def is_bulletins_year_index(url: str) -> bool:
    p = urlparse(url).path
    return "/operational-bulletins-manuals/bulletins-" in p and p.endswith(".html")

def keep(url: str) -> bool:
    u = url.strip()
    if not u:
        return False

    if is_bulletins_year_index(u):
        return False

    for bad in DROP_CONTAINS:
        if bad in u:
            return False

    return any(k in u for k in KEEP_CONTAINS)

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    kept = sorted(set(u for u in urls if keep(u)))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for u in kept:
            f.write(u + "\n")

    print(f"Input: {len(urls)} URLs")
    print(f"Kept:  {len(kept)} URLs")
    print(f"Saved: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
