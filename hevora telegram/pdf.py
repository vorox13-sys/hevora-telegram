import io
from pypdf import PdfReader # requirements.txt içine pypdf eklemelisin

def read_pdf_from_bytes(file_bytes: bytes) -> str:
    """PDF bayt verilerini okur ve içindeki metni birleştirip döndürür."""
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.strip()
    except Exception as e:
        return f"PDF okunurken hata oluştu: {str(e)}"
