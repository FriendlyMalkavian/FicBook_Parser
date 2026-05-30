import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
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
        parent_tag = fandom_section.find_parent()
        if parent_tag:
            fandoms = [
                a.get_text(strip=True)
                for a in parent_tag.find_all("a")
            ]
    meta["fandoms"] = fandoms

    tags = []
    tags_container = soup.find("div", class_="tags")
    if tags_container:
        tags = [a.get_text(strip=True) for a in tags_container.find_all("a")]
    meta["tags"] = tags

    for key in ("size", "status", "rating"):
        label = soup.find(string=re.compile(
            {"size": "Размер", "status": "Статус", "rating": "Рейтинг"}[key],
            re.IGNORECASE,
        ))
        if label:
            parent_tag = label.find_parent()
            if parent_tag:
                text = parent_tag.get_text(" ", strip=True).replace(" ", " ")
                meta[key] = text

    return meta


def fetch_part(url: str) -> tuple[str, str]:
    soup = fetch_soup(url)
    title_tag = soup.find("h2", itemprop="headline")
    part_title = title_tag.get_text(strip=True) if title_tag else ""
    text = extract_part_text(soup)
    return part_title, text


@dataclass
class FicData:
    id: str
    title: str = ""
    author: str = ""
    description: str = ""
    fandoms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    parts: list[dict] = field(default_factory=list)


def collect_fic(url_or_id: str) -> FicData:
    fic_id = get_fic_id(url_or_id)
    main_url = f"{BASE_URL}/readfic/{fic_id}"
    print(f"[*] Загружаю страницу: {main_url}", file=sys.stderr)

    soup = fetch_soup(main_url)
    meta = extract_metadata(soup)
    data = FicData(id=fic_id, **{k: v for k, v in meta.items() if k in FicData.__dataclass_fields__})

    part_links = parse_part_links(soup)

    if not part_links:
        print("[*] Фанфик без частей, загружаю текст с основной страницы", file=sys.stderr)
        text = extract_part_text(soup)
        if text:
            data.parts.append({"title": "", "text": text})
    else:
        print(f"[*] Найдено частей: {len(part_links)}", file=sys.stderr)
        for i, (href, part_title) in enumerate(part_links, 1):
            part_url = f"{BASE_URL}{href}" if href.startswith("/") else href
            print(f"  [{i}/{len(part_links)}] {part_title or href}", file=sys.stderr)
            p_title, text = fetch_part(part_url)
            data.parts.append({"title": p_title, "text": text})

    return data


def save_txt(data: FicData, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{'='*60}\n")
        f.write(f"  {data.title}\n")
        f.write(f"  Автор: {data.author}\n")
        if data.description:
            f.write(f"\n  Описание: {data.description}\n")
        if data.fandoms:
            f.write(f"  Фэндомы: {', '.join(data.fandoms)}\n")
        if data.tags:
            f.write(f"  Метки: {', '.join(data.tags)}\n")
        f.write(f"{'='*60}\n\n")

        for i, part in enumerate(data.parts, 1):
            f.write(f"{'─'*40}\n")
            f.write(f"  Часть {i}")
            if part["title"]:
                f.write(f": {part['title']}")
            f.write(f"\n{'─'*40}\n\n")
            if part["text"]:
                f.write(part["text"])
            f.write("\n\n")


def save_md(data: FicData, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {data.title}\n\n")
        f.write(f"**Автор:** {data.author}\n\n")
        if data.description:
            f.write(f"{data.description}\n\n")
        if data.fandoms:
            f.write(f"**Фэндомы:** {', '.join(data.fandoms)}\n\n")
        if data.tags:
            f.write(f"**Метки:** {', '.join(data.tags)}\n\n")
        f.write("---\n\n")

        for i, part in enumerate(data.parts, 1):
            title = part["title"] or f"Часть {i}"
            f.write(f"## {title}\n\n")
            if part["text"]:
                f.write(part["text"])
            f.write("\n\n---\n\n")


def save_json(data: FicData, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(data), f, ensure_ascii=False, indent=2)


FORMATTERS = {
    "txt": save_txt,
    "md": save_md,
    "json": save_json,
}


def download_fic(url_or_id: str, output: str | None = None, fmt: str = "txt") -> str:
    data = collect_fic(url_or_id)

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", data.title)
    ext = fmt
    if fmt == "md":
        ext = "md"
    elif fmt == "json":
        ext = "json"
    else:
        ext = "txt"

    out_path = output or f"{safe_title}.{ext}"

    save = FORMATTERS.get(fmt)
    if not save:
        raise ValueError(f"Неизвестный формат: {fmt}")
    save(data, out_path)

    print(f"\n[✓] Сохранено в: {out_path}", file=sys.stderr)
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Скачать фанфик с ficbook.net"
    )
    parser.add_argument(
        "url",
        help="URL фанфика (например, https://ficbook.net/readfic/1081615) или ID",
    )
    parser.add_argument(
        "-o", "--output",
        help="Путь для сохранения (по умолчанию: название_фанфика.формат)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["txt", "md", "json"],
        default="txt",
        help="Формат вывода: txt (по умолчанию), md (markdown), json",
    )

    args = parser.parse_args()
    download_fic(args.url, args.output, args.format)


if __name__ == "__main__":
    main()
