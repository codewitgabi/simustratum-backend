from api.v1.services.document_service import CHUNK_OVERLAP, CHUNK_SIZE, chunk_text, extract_text


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_single_chunk_when_short():
    text = "word " * 50
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == " ".join(["word"] * 50)


def test_chunk_text_splits_long_text_with_overlap():
    words = [f"w{i}" for i in range(2000)]
    text = " ".join(words)
    chunks = chunk_text(text)

    assert len(chunks) > 1
    # consecutive chunks overlap by CHUNK_OVERLAP words
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    step = CHUNK_SIZE - CHUNK_OVERLAP
    assert first_words[step:] == second_words[: CHUNK_SIZE - step]


def test_extract_text_txt():
    assert extract_text("notes.txt", b"hello world") == "hello world"


def test_extract_text_unsupported_extension_raises():
    import pytest

    from api.v1.services.document_service import UnsupportedDocumentError

    with pytest.raises(UnsupportedDocumentError):
        extract_text("audio.mp3", b"not text")
