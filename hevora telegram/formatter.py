import re

TELEGRAM_LIMIT = 4096


def split_message(text, limit=TELEGRAM_LIMIT):
    return [
        text[i:i + limit]
        for i in range(0, len(text), limit)
    ]


def convert_tables(text):
    lines = text.split("\n")

    new = []

    inside = False

    table = []

    for line in lines:

        if "|" in line:

            table.append(line)

            inside = True

        else:

            if inside:

                new.append(table_to_box(table))

                table = []

                inside = False

            new.append(line)

    if table:

        new.append(table_to_box(table))

    return "\n".join(new)


def table_to_box(lines):

    rows = []

    for l in lines:

        if "---" in l:
            continue

        cols = [c.strip() for c in l.split("|") if c.strip()]

        rows.append(cols)

    if not rows:
        return ""

    widths = []

    for i in range(len(rows[0])):
        widths.append(
            max(len(r[i]) for r in rows)
        )

    out = []

    top = "┌" + "┬".join(
        "─"*(w+2)
        for w in widths
    ) + "┐"

    out.append(top)

    for i,row in enumerate(rows):

        out.append(
            "│ " +
            " │ ".join(
                row[j].ljust(widths[j])
                for j in range(len(widths))
            ) +
            " │"
        )

        if i==0:

            out.append(
                "├"+"┼".join(
                    "─"*(w+2)
                    for w in widths
                )+"┤"
            )

    out.append(
        "└"+"┴".join(
            "─"*(w+2)
            for w in widths
        )+"┘"
    )

    return "\n".join(out)


def format_markdown(text):

    text = convert_tables(text)

    return text