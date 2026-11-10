"""TypeKeep text sanitising - v3.3.0.

Why this exists: on Windows, some input paths (emoji panels, IME, dead
keys, certain apps) hand pynput *lone UTF-16 surrogate halves* such as
'\\ud83d' instead of a real character. Python's sqlite3 encodes text as
UTF-8 and raises

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d':
    surrogates not allowed

for those strings. Before v3.3.0 a single poisoned event made the whole
buffered batch fail, the batch was re-queued, and it then failed forever -
silently blocking (losing) every keystroke typed after it. The live log
showed exactly that error repeating for weeks.

clean_text() repairs what is repairable and neutralises the rest:
- a valid high+low surrogate pair is combined into the real character
  (so an emoji typed as a pair is kept as that emoji),
- an unpaired surrogate is replaced with U+FFFD (visible, harmless),
- NUL bytes are stripped (they truncate C-side strings),
- anything else passes through untouched.

It is deliberately cheap: strings without surrogates/NULs (99.99% of
keystrokes) return after a single scan of two ``in`` checks.
"""

_REPLACEMENT = '\ufffd'


def _has_bad_char(text):
    if '\x00' in text:
        return True
    for ch in text:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            return True
    return False


def clean_text(value):
    """Return a UTF-8-safe version of *value* (non-strings pass through)."""
    if not isinstance(value, str):
        return value
    if not _has_bad_char(value):
        return value
    out = []
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        code = ord(ch)
        if ch == '\x00':
            i += 1
            continue
        if 0xD800 <= code <= 0xDBFF:  # high surrogate
            if i + 1 < n and 0xDC00 <= ord(value[i + 1]) <= 0xDFFF:
                low = ord(value[i + 1])
                out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                i += 2
                continue
            out.append(_REPLACEMENT)
            i += 1
            continue
        if 0xDC00 <= code <= 0xDFFF:  # lone low surrogate
            out.append(_REPLACEMENT)
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def was_cleaned(original, cleaned):
    return isinstance(original, str) and original != cleaned
