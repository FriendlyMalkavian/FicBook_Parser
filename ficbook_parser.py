import argparse
import html
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from xml.etree import ElementTree as ET

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


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_to_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in clean_text(text).split("\n\n") if p.strip()]


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
            if i > 1 and len(part_links) > 5:
                print("  Пауза 5 сек…", file=sys.stderr)
                time.sleep(5)
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
            f.write(clean_text(part["text"]))
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
            f.write(clean_text(part["text"]))
            f.write("\n\n---\n\n")


def save_json(data: FicData, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(data), f, ensure_ascii=False, indent=2)


def save_epub(data: FicData, path: str):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(data.title)
    book.set_language("ru")
    book.add_author(data.author)

    if data.description:
        book.add_metadata("DC", "description", data.description)

    css = """
    @namespace epub "http://www.idpf.org/2007/ops";
    body { font-family: serif; line-height: 1.6; margin: 1em 2em; }
    h1, h2 { text-align: center; }
    p { text-indent: 1.25em; margin: 0; }
    .title-page { text-align: center; margin-top: 20%; }
    .title-page h1 { font-size: 1.8em; }
    .title-page .author { font-size: 1.2em; margin-top: 1em; }
    .title-page .meta { font-size: 0.9em; color: #555; margin-top: 2em; }
    """
    css_item = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=css)
    book.add_item(css_item)

    chapters = []
    for i, part in enumerate(data.parts, 1):
        title = part["title"] or f"Часть {i}"
        paragraphs = text_to_paragraphs(part["text"])
        content = f"<h2>{html.escape(title)}</h2>\n"
        for p in paragraphs:
            content += f"<p>{html.escape(p)}</p>\n"

        chap = epub.EpubHtml(title=title, file_name=f"part_{i}.xhtml", lang="ru")
        chap.content = content
        chap.add_item(css_item)
        book.add_item(chap)
        chapters.append(chap)

    title_page_content = f"""
    <div class="title-page">
        <h1>{html.escape(data.title)}</h1>
        <p class="author">{html.escape(data.author)}</p>
    """
    if data.description:
        title_page_content += f'<p class="meta">{html.escape(data.description)}</p>'
    if data.fandoms:
        title_page_content += f'<p class="meta">Фэндомы: {html.escape(", ".join(data.fandoms))}</p>'
    if data.tags:
        title_page_content += f'<p class="meta">Метки: {html.escape(", ".join(data.tags))}</p>'
    title_page_content += "</div>"

    title_page = epub.EpubHtml(title="Начало", file_name="title.xhtml", lang="ru")
    title_page.content = title_page_content
    title_page.add_item(css_item)
    book.add_item(title_page)

    book.toc = [
        epub.Link("title.xhtml", "Начало", "title"),
    ] + [epub.Link(f"part_{i}.xhtml", p["title"] or f"Часть {i}", f"p{i}") for i, p in enumerate(data.parts, 1)]

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + [title_page] + chapters

    epub.write_epub(path, book, {})


def save_fb2(data: FicData, path: str):
    NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
    ET.register_namespace("", NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

    root = ET.Element(f"{{{NS}}}FictionBook")

    desc = ET.SubElement(root, f"{{{NS}}}description")
    ti = ET.SubElement(desc, f"{{{NS}}}title-info")

    _add_el(ti, NS, "genre", "fanfiction")
    _add_el(ti, NS, "author", ET.SubElement(ti, f"{{{NS}}}first-name"))
    last = ET.SubElement(ti, f"{{{NS}}}last-name")
    last.text = data.author

    _add_el(ti, NS, "book-title", data.title)

    if data.description:
        ann = ET.SubElement(ti, f"{{{NS}}}annotation")
        ann_p = ET.SubElement(ann, f"{{{NS}}}p")
        ann_p.text = data.description

    _add_el(ti, NS, "lang", "ru")

    for tag in data.tags:
        _add_el(ti, NS, "keywords", tag)

    doc_info = ET.SubElement(desc, f"{{{NS}}}document-info")
    _add_el(doc_info, NS, "id", str(uuid.uuid4()))

    body = ET.SubElement(root, f"{{{NS}}}body")

    if data.title:
        title_sec = ET.SubElement(body, f"{{{NS}}}section")
        _add_el(title_sec, NS, "title", data.title)
        if data.author:
            ep = ET.SubElement(title_sec, f"{{{NS}}}epigraph")
            ea = ET.SubElement(ep, f"{{{NS}}}author")
            ea.text = data.author

    for i, part in enumerate(data.parts, 1):
        sec = ET.SubElement(body, f"{{{NS}}}section")
        title = part["title"] or f"Часть {i}"
        _add_el(sec, NS, "title", title)

        paragraphs = text_to_paragraphs(part["text"])
        for p_text in paragraphs:
            _add_el(sec, NS, "p", p_text)

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _add_el(parent, ns, tag, text=None):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        el.text = text
    return el


FORMATTERS = {
    "txt": save_txt,
    "md": save_md,
    "json": save_json,
    "epub": save_epub,
    "fb2": save_fb2,
}


def download_fic(url_or_id: str, output: str | None = None, fmt: str = "txt") -> str:
    data = collect_fic(url_or_id)

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", data.title)
    out_path = output or f"{safe_title}.{fmt}"

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
        choices=["txt", "md", "json", "epub", "fb2"],
        default="txt",
        help="Формат вывода: txt (по умолчанию), md, json, epub, fb2",
    )

    args = parser.parse_args()
    download_fic(args.url, args.output, args.format)


if __name__ == "__main__":
    main()
