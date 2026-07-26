import re
import html
from wcwidth import wcswidth

TELEGRAM_LIMIT = 4096

# ==========================================================
# HTML ESCAPE
# ==========================================================

def escape(text: str) -> str:
    return html.escape(text, quote=False)


# ==========================================================
# MESSAGE SPLITTER
# ==========================================================

def split_message(text, limit=TELEGRAM_LIMIT):
    parts = []
    while len(text) > limit:
        pos = text.rfind("\n", 0, limit)
        if pos == -1:
            pos = limit
        parts.append(text[:pos])
        text = text[pos:]
    if text:
        parts.append(text)
    return parts


# ==========================================================
# CODE BLOCK STORAGE
# ==========================================================

CODE_PATTERN = re.compile(
    r"```([a-zA-Z0-9]*)\n([\s\S]*?)```"
)

INLINE_PATTERN = re.compile(
    r"`([^`\n]+)`"
)


def extract_code_blocks(text):
    blocks = []

    def repl(match):
        code = match.group(2)
        token = f"@@CODEBLOCK_{len(blocks)}@@"
        blocks.append(
            (
                token,
                "<pre><code>"
                + escape(code)
                + "</code></pre>"
            )
        )
        return token

    text = CODE_PATTERN.sub(repl, text)
    return text, blocks


def extract_inline_code(text):
    blocks = []

    def repl(match):
        code = match.group(1)
        token = f"@@INLINE_{len(blocks)}@@"
        blocks.append(
            (
                token,
                "<code>"
                + escape(code)
                + "</code>"
            )
        )
        return token

    text = INLINE_PATTERN.sub(repl, text)
    return text, blocks


def restore_tokens(text, blocks):
    for token, value in blocks:
        text = text.replace(token, value)
    return text


# ==========================================================
# TABLE CONVERTER (GELİŞTİRİLMİŞ VE DÜZGÜN HİZALANMIŞ)
# ==========================================================

TABLE_SEPARATOR = re.compile(r"^\s*\|?[\-\:\| ]+\|?\s*$")


def convert_tables(text):
    lines = text.split("\n")
    result = []
    table = []

    def is_table_line(line):
        return "|" in line

    for line in lines:
        if is_table_line(line):
            table.append(line)
            continue
        
        if table:
            result.append(table_to_box(table))
            table = []

        result.append(line)

    if table:
        result.append(table_to_box(table))

    return "\n".join(result)


def table_to_box(lines):
    rows = []
    has_header = False

    for i, line in enumerate(lines):
        if TABLE_SEPARATOR.match(line):
            has_header = True
            continue

        cols = [c.strip() for c in line.strip().split("|")]
        if cols and cols[0] == "":
            cols.pop(0)
        if cols and cols[-1] == "":
            cols.pop()
        
        if cols:
            rows.append(cols)

    if not rows:
        return ""

    column_count = max(len(r) for r in rows)
    for row in rows:
        while len(row) < column_count:
            row.append("")

    widths = []
    for col in range(column_count):
        width = 0
        for row in rows:
            width = max(width, visual_width(row[col]))
        widths.append(width)

    out = []

    # Üst çizgi
    out.append(
        "┌" +
        "┬".join(
            "─" * (w + 2)
            for w in widths
        ) +
        "┐"
    )

    for index, row in enumerate(rows):
        cells = []
        # Eğer başlık ayrıcı yoksa ama ilk satır headersa mantığına göre index 0 başlık sayılabilir
        is_header_row = has_header and index == 0

        for i, cell in enumerate(row):
            if is_header_row:
                cells.append(center_pad(cell, widths[i]))
            else:
                cells.append(pad(cell, widths[i]))

        out.append(
            "│ " +
            " │ ".join(cells) +
            " │"
        )

        # Başlık altı çizgisi
        if has_header and index == 0:
            out.append(
                "├" +
                "┼".join(
                    "─" * (w + 2)
                    for w in widths
                ) +
                "┤"
            )

    # Alt çizgi
    out.append(
        "└" +
        "┴".join(
            "─" * (w + 2)
            for w in widths
        ) +
        "┘"
    )

    # Tabloların <pre> etiketleri arasına alınması, escape edilmeden doğrudan basılması gerekir
    # Böylece karakterler bozulmaz.
    return "<pre>" + "\n".join(out) + "</pre>"


def visual_width(text):
    w = wcswidth(str(text))
    return w if w >= 0 else len(str(text))


def pad(text, width):
    text = str(text)
    return text + " " * max(0, width - visual_width(text))


def center_pad(text, width):
    text = str(text)
    diff = width - visual_width(text)
    if diff <= 0:
        return text
    left = diff // 2
    right = diff - left
    return " " * left + text + " " * right


# ==========================================================
# MARKDOWN -> HTML (TEK VE GÜNCEL FONKSİYON)
# ==========================================================

def markdown_to_html(text):
    # <pre> bloklarını (Tablolar dahil) koruma altına al
    pre_blocks = []

    def save_pre(match):
        token = f"@@PRE_{len(pre_blocks)}@@"
        pre_blocks.append(match.group(0))
        return token

    text = re.sub(r"<pre>[\s\S]*?</pre>", save_pre, text)

    # Normal metni escape et
    text = escape(text)

    # Başlıklar
    text = re.sub(r"^### (.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Kalın
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # İtalik
    text = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<i>\1</i>", text)

    # Altı çizili
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)

    # Üstü çizili
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Maddeler
    text = re.sub(r"^- (.+)$", r"• \1", text, flags=re.MULTILINE)

    # Numaralı
    text = re.sub(r"^\d+\. (.+)$", r"◦ \1", text, flags=re.MULTILINE)

    # Alıntı
    text = re.sub(r"^&gt; (.+)$", r"│ \1", text, flags=re.MULTILINE)

    # Link
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    # Korumaya alınan <pre> (tablo ve kod) bloklarını geri yükle (Escape işleminden etkilenmezler)
    for i, block in enumerate(pre_blocks):
        text = text.replace(f"@@PRE_{i}@@", block)

    return text


# ==========================================================
# FORMAT RESPONSE
# ==========================================================

def format_response(text: str):
    # 1. Kod bloklarını koru
    text, code_blocks = extract_code_blocks(text)

    # 2. Inline kodları koru
    text, inline_blocks = extract_inline_code(text)

    # 3. Markdown tablolarını kutu formatına (<pre> içinde) çevir
    text = convert_tables(text)

    # 4. Kalan Markdown yapılarını HTML'e çevir (Tablolar <pre> içinde olduğu için bozulmaz)
    text = markdown_to_html(text)

    # 5. Kod bloklarını geri koy
    text = restore_tokens(text, code_blocks)

    # 6. Inline kodları geri koy
    text = restore_tokens(text, inline_blocks)

    # 7. Telegram karakter sınırına göre böl
    parts = split_message(text)

    return parts, "HTML"
