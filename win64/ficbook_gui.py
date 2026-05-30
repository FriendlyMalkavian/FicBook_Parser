import html
import json
import re
import sys
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from tkinter import *
from tkinter import ttk, messagebox
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
    parts = []
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
    return content_div.get_text("\n") if content_div else ""


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
            fandoms = [a.get_text(strip=True) for a in parent_tag.find_all("a")]
    meta["fandoms"] = fandoms
    tags = []
    tags_container = soup.find("div", class_="tags")
    if tags_container:
        tags = [a.get_text(strip=True) for a in tags_container.find_all("a")]
    meta["tags"] = tags
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


def collect_fic(url_or_id: str, status_callback=None) -> FicData:
    fic_id = get_fic_id(url_or_id)
    main_url = f"{BASE_URL}/readfic/{fic_id}"
    _log(status_callback, f"Загружаю страницу: {main_url}")

    soup = fetch_soup(main_url)
    meta = extract_metadata(soup)
    data = FicData(
        id=fic_id,
        **{k: v for k, v in meta.items() if k in FicData.__dataclass_fields__}
    )

    part_links = parse_part_links(soup)

    if not part_links:
        _log(status_callback, "Фанфик без частей, загружаю текст с основной страницы")
        text = extract_part_text(soup)
        if text:
            data.parts.append({"title": "", "text": text})
    else:
        _log(status_callback, f"Найдено частей: {len(part_links)}")
        for i, (href, part_title) in enumerate(part_links, 1):
            part_url = f"{BASE_URL}{href}" if href.startswith("/") else href
            _log(status_callback, f"  [{i}/{len(part_links)}] {part_title or href}")
            p_title, text = fetch_part(part_url)
            data.parts.append({"title": p_title, "text": text})

    return data


def _log(callback, msg):
    if callback:
        callback(msg)


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
        content = f"<h2>{_e(title)}</h2>\n"
        for p in paragraphs:
            content += f"<p>{_e(p)}</p>\n"
        chap = epub.EpubHtml(title=title, file_name=f"part_{i}.xhtml", lang="ru")
        chap.content = content
        chap.add_item(css_item)
        book.add_item(chap)
        chapters.append(chap)

    title_html = f"""
    <div class="title-page">
        <h1>{_e(data.title)}</h1>
        <p class="author">{_e(data.author)}</p>
    """
    if data.description:
        title_html += f'<p class="meta">{_e(data.description)}</p>'
    if data.fandoms:
        title_html += f'<p class="meta">Фэндомы: {_e(", ".join(data.fandoms))}</p>'
    if data.tags:
        title_html += f'<p class="meta">Метки: {_e(", ".join(data.tags))}</p>'
    title_html += "</div>"

    title_page = epub.EpubHtml(title="Начало", file_name="title.xhtml", lang="ru")
    title_page.content = title_html
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
        for p_text in text_to_paragraphs(part["text"]):
            _add_el(sec, NS, "p", p_text)

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _add_el(parent, ns, tag, text=None):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _e(text: str) -> str:
    return html.escape(text)


# ─── GUI ─────────────────────────────────────

class FicbookApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FicBook Parser")
        self.root.resizable(False, False)

        try:
            self.root.iconbitmap(sys.executable)
        except Exception:
            pass

        main = ttk.Frame(root, padding=16)
        main.pack(fill=BOTH, expand=True)

        ttk.Label(main, text="Ссылка на фанфик:").grid(row=0, column=0, sticky=W, pady=(0, 4))
        self.url_var = StringVar()
        self.url_entry = ttk.Entry(main, textvariable=self.url_var, width=60)
        self.url_entry.grid(row=1, column=0, columnspan=3, sticky=EW, pady=(0, 12))
        self.url_entry.focus()

        ttk.Label(main, text="Формат:").grid(row=2, column=0, sticky=W, pady=(0, 4))
        self.fmt_var = StringVar(value="txt")
        fmts = [("TXT", "txt"), ("Markdown", "md"), ("JSON", "json"), ("EPUB", "epub"), ("FB2", "fb2")]
        for idx, (label, val) in enumerate(fmts):
            ttk.Radiobutton(main, text=label, variable=self.fmt_var, value=val).grid(
                row=3, column=idx, sticky=W, padx=(0, 8)
            )

        self.go_btn = ttk.Button(main, text="Загрузить", command=self.start_download)
        self.go_btn.grid(row=4, column=0, columnspan=5, pady=16)
        self.go_btn.configure(width=30)

        self._add_context_menu(self.url_entry)

        self.status = StringVar()
        status_lbl = ttk.Label(main, textvariable=self.status, wraplength=520, foreground="#555")
        status_lbl.grid(row=5, column=0, columnspan=5, sticky=W, pady=(0, 4))

        self.progress = ttk.Progressbar(main, mode="indeterminate", length=520)
        self.progress.grid(row=6, column=0, columnspan=5, sticky=EW)

        self.root.columnconfigure(0, weight=1)

    def _add_context_menu(self, widget):
        menu = Menu(self.root, tearoff=0)
        menu.add_command(label="Вырезать", command=lambda: self.root.focus_get().event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: self.root.focus_get().event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: self.root.focus_get().event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Очистить", command=lambda: widget.delete(0, END))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)
            menu.grab_release()

        widget.bind("<Button-3>", show_menu)
        widget.bind("<Button-2>", show_menu)

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Ошибка", "Введите ссылку на фанфик")
            return
        self.go_btn.configure(state=DISABLED)
        self.progress.start()
        self.set_status("Начинаю загрузку…")
        threading.Thread(target=self.download, args=(url,), daemon=True).start()

    def download(self, url):
        fmt = self.fmt_var.get()
        try:
            data = collect_fic(url, status_callback=self.set_status)
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", data.title)
            downloads = Path.home() / "Downloads"
            out_path = str(downloads / f"{safe_title}.{fmt}")
            FORMATTERS[fmt](data, out_path)
            self.root.after(0, lambda: self.done(True, out_path))
        except Exception as e:
            self.root.after(0, lambda: self.done(False, str(e)))

    def done(self, ok, msg):
        self.progress.stop()
        self.go_btn.configure(state=NORMAL)
        if ok:
            self.set_status(f"Готово: {msg}")
            messagebox.showinfo("Успешно", f"Фанфик сохранён:\n{msg}")
        else:
            self.set_status(f"Ошибка: {msg}")
            messagebox.showerror("Ошибка", msg)

    def set_status(self, msg):
        self.root.after(0, lambda: self.status.set(msg))


FORMATTERS = {
    "txt": save_txt,
    "md": save_md,
    "json": save_json,
    "epub": save_epub,
    "fb2": save_fb2,
}


def main():
    root = Tk()
    FicbookApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
