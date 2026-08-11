import re


_LEGAL_SUFFIXES = {
    'CO', 'COMPANY', 'CORP', 'CORPORATION', 'GMBH', 'INC',
    'INCORPORATED', 'LIMITED', 'LLC', 'LTD', 'PLC',
}


def generated_supplier_short_name(value):
    """Create a compact display name without changing the stored legal name."""
    text = str(value or '').strip()
    if not text:
        return ''

    text = re.sub(r'\([^)]*\)|\[[^]]*\]|\{[^}]*\}', ' ', text)
    words = []
    for word in re.split(r'\s+', text):
        cleaned = re.sub(r'[^\w&-]', '', word)
        if cleaned and cleaned.upper() not in _LEGAL_SUFFIXES:
            words.append(cleaned)

    if not words:
        return text[:64]
    if len(words) > 2:
        return ''.join(word[0] for word in words[:4]).upper()
    return ' '.join(words)[:64]
