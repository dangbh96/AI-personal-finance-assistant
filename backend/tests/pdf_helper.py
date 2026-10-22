"""Sinh PDF tối giản có lớp chữ (Helvetica, ASCII) cho test ingest PDF, không cần thư viện ngoài."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str], title: str | None = None) -> bytes:
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    content_ids = [5 + 2 * i for i in range(n)]
    info_id = 4 + 2 * n
    objs: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(pages):
        body = " ".join(f"({_escape(line)}) Tj T*" for line in text.split("\n"))
        stream = f"BT /F1 11 Tf 14 TL 72 740 Td {body} ET"
        objs[page_ids[i]] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ids[i]} 0 R >>"
        )
        objs[content_ids[i]] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    if title:
        objs[info_id] = f"<< /Title ({_escape(title)}) >>"

    out = b"%PDF-1.4\n"
    offsets: dict[int, int] = {}
    for key in sorted(objs):
        offsets[key] = len(out)
        out += f"{key} 0 obj\n{objs[key]}\nendobj\n".encode("latin-1")
    xref = len(out)
    size = max(objs) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for key in range(1, size):
        entry = f"{offsets[key]:010d} 00000 n \n" if key in offsets else "0000000000 65535 f \n"
        out += entry.encode()
    info = f" /Info {info_id} 0 R" if title else ""
    out += f"trailer\n<< /Size {size} /Root 1 0 R{info} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out
