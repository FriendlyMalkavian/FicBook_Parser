import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ficbook.net"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "lxml")


def get_fic_id(url_or_id: str) -> str:
    match = re.search(r"/readfic/([^/?#]+)", url_or_id)
    if match:
        return match.group(1)
    if re.match(r"^[\da-f-]+$", url_or_id, re.IGNORECASE):
        return url_or_id
    raise ValueError(f"Не удалось распознать ID фанфика из: {url_or_id}")


def parse_part_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    ul = soup.find("ul", class_="list-of-fanfic-parts")
    if not ul:
        return []

    parts: list[tuple[str, str]] = []
    for li in ul.find_all("li", class_="part"):
        a = li.find("a", class_="part-link")
        if a and a.get("href"):
            href = a["href"].split("#")[0]
            title_tag = a.find("h3")
            title = title_tag.get_text(strip=True) if title_tag else ""
            parts.append((href, title))
    return parts


def extract_part_text(soup: BeautifulSoup) -> str:
    content_div = soup.find("div", id="content", class_="js-part-text")
    if not content_div:
        return ""
    return content_div.get_text("\n")


def extract_metadata(soup: BeautifulSoup) -> dict:
    meta = {}
    title_h1 = soup.find("h1", class_="heading")
    if title_h1:
        meta["title"] = title_h1.get_text(strip=True)

    author_link = soup.find("a", class_="creator-username")
    if author_link:
        meta["author"] = author_link.get_text(strip=True)

    desc_div = soup.find("div", class_="js-public-beta-description")
    if desc_div:
        meta["description"] = desc_div.get_text(strip=True)

    fandoms = []
    fandom_section = soup.find(string=re.compile("Фэндом"))
    if fandom_section:
        parent = fandom_section.find_parent()
        if parent:
            fandoms = [
                a.get_text(strip=True)
                for a in parent.find_all("a")
            ]
    meta["fandoms"] = fandoms

    tags = []
    tags_container = soup.find("div", class_="tags")
    if tags_container:
        tags = [a.get_text(strip=True) for a in tags_container.find_all("a")]
    meta["tags"] = tags

    return meta


def fetch_part(url: str) -> tuple[str, str, str]:
    soup = fetch_soup(url)
    title_tag = soup.find("h2", itemprop="headline")
    part_title = title_tag.get_text(strip=True) if title_tag else ""
    text = extract_part_text(soup)
    prev_link = ""
    next_link = ""

    nav = soup.find("nav", class_="navigation-to-fanfic-parts-container")
    if nav:
        links = nav.find_all("a")
        for link in links:
            href = link.get("href", "")
            if "btn-next" in link.get("class", []) or "Вперёд" in link.get_text():
                next_link = href.split("#")[0]
            elif "Назад" in link.get_text() and "/readfic/" in href:
                prev_link = href.split("#")[0]
    return part_title, text, next_link


def download_fic(url_or_id: str, output: str | None = None) -> str:
    fic_id = get_fic_id(url_or_id)
    main_url = f"{BASE_URL}/readfic/{fic_id}"
    print(f"[*] Загружаю страницу: {main_url}", file=sys.stderr)

    soup = fetch_soup(main_url)
    meta = extract_metadata(soup)
    title = meta.get("title", f"Фанфик_{fic_id}")
    author = meta.get("author", "Неизвестен")

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
    out_path = output or f"{safe_title}.txt"

    part_links = parse_part_links(soup)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{'='*60}\n")
        f.write(f"  {title}\n")
        f.write(f"  Автор: {author}\n")
        if meta.get("description"):
            f.write(f"\n  Описание: {meta['description']}\n")
        if meta.get("fandoms"):
            f.write(f"  Фэндомы: {', '.join(meta['fandoms'])}\n")
        if meta.get("tags"):
            f.write(f"  Метки: {', '.join(meta['tags'])}\n")
        f.write(f"{'='*60}\n\n")

        if not part_links:
            print("[*] Фанфик без частей, загружаю текст с основной страницы", file=sys.stderr)
            text = extract_part_text(soup)
            if text:
                f.write(text)
            else:
                print("[!] Текст не найден на странице", file=sys.stderr)
        else:
            print(f"[*] Найдено частей: {len(part_links)}", file=sys.stderr)
            for i, (href, part_title) in enumerate(part_links, 1):
                part_url = f"{BASE_URL}{href}" if href.startswith("/") else href
                print(f"  [{i}/{len(part_links)}] {part_title or href}", file=sys.stderr)
                p_title, text, _ = fetch_part(part_url)
                f.write(f"{'─'*40}\n")
                f.write(f"  Часть {i}")
                if p_title:
                    f.write(f": {p_title}")
                f.write(f"\n{'─'*40}\n\n")
                if text:
                    f.write(text)
                f.write("\n\n")

    print(f"\n[✓] Сохранено в: {out_path}", file=sys.stderr)
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Скачать фанфик с ficbook.net"
    )
    parser.add_argument(
        "url",
        help="URL фанфика (например, https://ficbook.net/readfic/1081615) или числовой ID",
    )
    parser.add_argument(
        "-o", "--output",
        help="Путь для сохранения (по умолчанию: название_фанфика.txt)",
    )

    args = parser.parse_args()
    download_fic(args.url, args.output)


if __name__ == "__main__":
    main()
