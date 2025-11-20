import fitz
from prism.pdf_loader import extract_text_from_attachment


def create_sample_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Abstract\n"
        "This is abstract line 1\n"
        "And line 2\n"
        "Introduction\n"
        "This is body\n"
        "References\n"
    )
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_extract_text_from_attachment(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    create_sample_pdf(pdf_path)
    result = extract_text_from_attachment(str(pdf_path))
    sections = result["sections"]
    assert sections["abstract"] == "This is abstract line 1 And line 2"
    assert "This is body" in sections["main_body"]
    assert sections["pre_intro"]
