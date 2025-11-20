import requests
from requests.exceptions import RequestException
from io import BytesIO
import fitz
import re
import os
import time

# -----------------------------------------------------------
# download_pdf
# Downloads a PDF from a web URL and loads it into a fitz Document.
# IN: url (str)
# OUT: fitz.Document (opened PDF)
# -----------------------------------------------------------
def download_pdf(url, timeout=10, retries=3, backoff_factor=1.0):
    for attempt in range(retries):
        try:
            res = requests.get(url, timeout=timeout)
            res.raise_for_status()
            return fitz.open(stream=BytesIO(res.content), filetype="pdf")
        except RequestException as exc:
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2 ** attempt)
                time.sleep(sleep_time)
            else:
                raise RuntimeError(
                    f"Failed to download PDF from {url}: {exc}"
                ) from exc


# -----------------------------------------------------------
# extract_text_and_lines
# Extracts the entire text and a list of stripped lines from a fitz Document.
# IN: doc (fitz.Document)
# OUT: (full_text (str), stripped_lines (list of str))
# -----------------------------------------------------------
def extract_text_and_lines(doc):
    pages = [page.get_text() for page in doc]
    full_text = "\n".join(pages)
    lines = full_text.splitlines()
    stripped = [ln.strip() for ln in lines]
    return full_text, stripped


# -----------------------------------------------------------
# find_index
# Finds the first line index in a list of lines that matches any regex pattern.
# Performs both raw and simplified (stripped of spaces, symbols) matching.
# IN: patterns (list of regex strings), lines (list of str)
# OUT: index (int) or None if not found
# -----------------------------------------------------------
def find_index(patterns, lines):
    lc = [ln.lower() for ln in lines]
    lc_simple = [re.sub(r"[=\s]+", "", ln.lower()) for ln in lines]
    for idx, (raw, simp) in enumerate(zip(lc, lc_simple)):
        for pat in patterns:
            if re.match(pat, raw) or re.match(pat, simp):
                return idx
    return None


# -----------------------------------------------------------
# extract_sections
# Given stripped lines and found indices, divides the paper into:
# - pre_intro (everything before abstract or intro)
# - abstract (as lines)
# - main_body (as lines)
# - end_matter (as lines, after end_idx)
# IN: stripped (list of str), abstract_idx (int), intro_idx (int), end_idx (int)
# OUT: (pre_intro, abstract, main_body, end_matter) (all lists of str)
# -----------------------------------------------------------
def extract_sections(stripped, abstract_idx, intro_idx, end_idx):
    if abstract_idx is not None or intro_idx is not None:
        first_break = min(i for i in (abstract_idx, intro_idx) if i is not None)
        pre_intro = stripped[:first_break]
    else:
        pre_intro = stripped[:50]

    def _first_after(start, patterns):
        j = find_index(patterns, stripped[start + 1:])
        return (start + 1 + j) if j is not None else None

    keywords_idx = find_index([
        r"^keywords?\b",
        r"^author\s+keywords?\b",
        r"^key\s*words?\b",
        r"^index\s+terms?\b",
        r"^jel\s+classification\b",
        r"^msc\s+classification\b",
    ], stripped)

    abstract = []
    if abstract_idx is not None:
        kw_after = keywords_idx if (keywords_idx is not None and keywords_idx > abstract_idx) else None
        intro_after = intro_idx if (intro_idx is not None and intro_idx > abstract_idx) else None

        numbered_after = _first_after(abstract_idx, [
            r"^[0-9]+\s*[\.)]?\s+[A-Z].*",
            r"^(?:[ivxlcdm]+)\s*[\.)]?\s+[A-Z].*",
            r"^[A-Z][A-Z\s]{3,}$",
        ]) if kw_after is None and intro_after is None else None

        candidates = [c for c in (kw_after, intro_after, numbered_after, len(stripped)) if c is not None]
        abs_end = min(candidates)

        header_line = stripped[abstract_idx]
        inline = re.match(r"(?i)abstract(?:[\s\u2013\u2014-]+)(.*)", header_line)
        if inline:
            abstract.append(inline.group(1).strip())
            abstract.extend(stripped[abstract_idx + 1:abs_end])
        else:
            abstract = stripped[abstract_idx + 1:abs_end]
    
    elif intro_idx is not None and intro_idx > 5:
        abstract = stripped[:intro_idx]

    body_start = intro_idx if intro_idx is not None else (abstract_idx + 1 if abstract_idx is not None else 0)
    body_end = end_idx if end_idx is not None else len(stripped)
    main_body = stripped[body_start:body_end]
    end_matter = stripped[end_idx + 1:] if end_idx is not None else []
    return pre_intro, abstract, main_body, end_matter

# -----------------------------------------------------------
# extract_metadata
# Extracts and constructs a metadata string from a PDF document and pre-intro.
# Attempts to detect publication year, outlet, and arXiv ID.
# IN: doc (fitz.Document), full_text (str), pre_intro (list of str)
# OUT: metadata_block (str)
# -----------------------------------------------------------
def extract_metadata(doc, full_text, pre_intro):
    meta_lines = []

    # -----------------------------------------------------------
    # PUBLICATION YEAR DETECTION
    # -----------------------------------------------------------
    meta = doc.metadata or {}
    for key in ("creationDate", "modDate"):
        val = meta.get(key, "")
        if val:
            m = re.search(r"(20\d{2}|19\d{2})", val)
            if m:
                meta_lines.append(f"Detected Publication Year: {m.group(1)}")
                break

    # -----------------------------------------------------------
    # BUILD SAFE ZONE FOR IDENTIFIER SEARCH
    # (avoids references / citations / end matter)
    # -----------------------------------------------------------
    id_chunks = []

    # 1) Pre-intro content (title page area)
    if pre_intro:
        id_chunks.append("\n".join(pre_intro))

    # 2) First page text
    if doc.page_count > 0:
        first_page = doc[0]
        id_chunks.append(first_page.get_text())

        # 3) First-page link annotations (strong signal)
        try:
            for link in first_page.get_links():
                uri = (link.get("uri") or "").strip()
                if uri:
                    id_chunks.append(uri)
        except Exception:
            pass

    id_text = "\n".join(id_chunks)

    # -----------------------------------------------------------
    # PUBLICATION OUTLET DETECTION
    # (arXiv vs. "publication in …")
    # -----------------------------------------------------------
    m = re.search(r"publication in ([A-Za-z &()\.\-]+)", "\n".join(pre_intro), re.IGNORECASE)
    if m:
        meta_lines.append(f"Detected Publication Outlet: {m.group(1).strip()}")

    # -----------------------------------------------------------
    # DOI + ARXIV IDENTIFIER DETECTION (SAFE ZONE)
    # -----------------------------------------------------------
    doi_pattern = r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b"
    arxiv_pattern = r"arxiv[:\s]*(\d{4}\.\d{4,5}(?:v\d+)?)"

    detected_doi = None
    detected_arxiv = None

    # DOI detection
    m = re.search(doi_pattern, id_text)
    if m:
        detected_doi = m.group(0)
        meta_lines.append(f"Detected DOI: {detected_doi}")
        meta_lines.append(f"Detected DOI URL: https://doi.org/{detected_doi}")

    # arXiv ID detection (safe zone)
    am = re.search(arxiv_pattern, id_text, re.IGNORECASE)
    if am:
        detected_arxiv = am.group(1)
        meta_lines.append(f"Detected arXiv ID: {detected_arxiv}")
        meta_lines.append(f"Detected arXiv URL: https://arxiv.org/abs/{detected_arxiv}")
    else:
        meta_lines.append("No arXiv ID detected.")

    text = "\n".join(pre_intro) + "\n" + full_text
    text_lower = text.lower()

    license_markers = [
        "creative commons",
        "cc by",
        "cc-by",
        "open access article",
        "open-access article",
        "open access",
        "distributed under the terms of the",
        "this is an open access article",
        "open access funded",
        "public domain",
        "u.s. government work",
    ]

    open_access = "No"
    for marker in license_markers:
        if marker in text_lower:
            open_access = "Yes"
            break

    if any("Detected Publication Outlet: arXiv" in line for line in meta_lines):
        open_access = "Yes"

    meta_lines.append(f"Detected Open Access: {open_access}")

    # -----------------------------------------------------------
    # FINAL RETURN
    # -----------------------------------------------------------
    return "\n".join(meta_lines) + "\n" if meta_lines else ""

# -----------------------------------------------------------
# extract_text_from_attachment
# Main function: given a file path (or Airtable-style dict with 'url'),
# loads the PDF, splits into major sections, and includes
# detected metadata/MSI info in pre-intro.
# IN: attachment (str or dict with 'url')
# OUT: dict with 'sections' (pre_intro, abstract, main_body, end_matter)
# -----------------------------------------------------------
def extract_text_from_attachment(attachment):
    if isinstance(attachment, str):
        doc = fitz.open(attachment)
    elif isinstance(attachment, dict) and "url" in attachment:
        url = attachment["url"]
        if os.path.exists(url):
            doc = fitz.open(url)
        else:
            doc = download_pdf(url)
    else:
        raise ValueError("Invalid attachment format")

    try:
        full_text, stripped = extract_text_and_lines(doc)

        abstract_idx = find_index(
            [
                r"^abstract[:\s]*$",
                r"^abstract[\s\u2013\u2014-].+",
                r"^summary[:\s]*$",
                r"^={2,}\s*abstract\s*={2,}$",
                r"^abstract\s*[:\-\u2013\u2014]\s*.+$",
                r"^summary\s*[:\-\u2013\u2014]\s*.+$",
                r"^#+\s*abstract\s*$",
                r"^\*\*abstract\*\*$",
            ],
            stripped,
        )

        intro_idx = find_index(
            [
                r"^[0-9]+\.?\s*introduction$",
                r"^[ivxlcdm]+\.?\s*introduction$",
                r"^section\s*[0-9]+[:\.]?\s*introduction$",
                r"^introduction$",
                r"^background$",
                r"^={2,}\s*introduction\s*={2,}$",
            ],
            stripped,
        )

        end_idx = find_index(
            [
                r"^references$",
                r"^reference$",
                r"^literature\s+cited$",
                r"^works\s+cited$",
                r"^bibliography$",
                r"^acknowledg(?:ements)?$",
                r"^appendix$",
                r"^supplementary$",
                r"^data\s+availability$",
                r"^conflicts\s+of\s+interest$",
                r"^funding$",
                r"^={2,}\s*(references|bibliography|acknowledg|appendix|supplementary)\s*={2,}$",
            ],
            stripped,
        )

        pre_intro, abstract, main_body, end_matter = extract_sections(
            stripped, abstract_idx, intro_idx, end_idx
        )
        meta_block = extract_metadata(doc, full_text, pre_intro)

        pre_intro_section = (meta_block + "\n".join(pre_intro)).strip()
        if not pre_intro_section:
            pre_intro_section = full_text

        return {
            "sections": {
                "pre_intro": pre_intro_section,
                "abstract": " ".join(
                    filter(None, (line.strip() for line in abstract))
                ).strip(),
                "main_body": "\n".join(main_body).strip(),
                "end_matter": "\n".join(end_matter).strip(),
            },
            "full_text": full_text
        }
    finally:
        doc.close()
