# Attachment Processing

Use this reference after `mac_mail_local_triage.py read` has exported the
message body and attachment bytes to a local temporary directory.

## Required Sequence

1. Preserve the original exported file and record `name`, `content_type`,
   `size`, and `sha256` from the `read` JSON.
2. Detect the real file type from the bytes as well as the extension. Never
   infer a document type from the filename alone.
3. Extract facts with a source location and confidence. Keep the original
   value and the normalized value separate.
4. If parsing fails, the file is encrypted, or only part of the file was read,
   set the source to `BLOCKED` and stop before a WMS write.

## File Types

| Type | Required inspection | Evidence location |
| --- | --- | --- |
| `.eml` / `message/rfc822` | Parse headers, body, inline content, and nested attachments recursively | nested Message-ID, header, body section, attachment name |
| PDF | Extract text from every page; render or OCR image-only pages | page number, table/region, OCR confidence |
| XLSX / XLS | Inspect every visible and hidden sheet, used range, hidden rows/columns, formulas and displayed values | workbook, sheet, cell/range |
| CSV / TSV | Decode with the detected or declared encoding and inspect every row, including trailing columns | file, row, column |
| TXT / HTML | Read the complete file, including quoted or forwarded sections | file, line or section |
| JPEG / PNG / TIFF | Visually inspect and OCR when needed; preserve uncertainty for blurred or cut-off text | file, image region, OCR confidence |

For a workbook, do not stop at the first sheet or the first non-empty table.
For an image, do not claim a serial number, quantity, or date that is not
legible. For nested mail, the outer email is still the source package and the
nested Message-ID and attachment hashes must be retained as child evidence.

## Evidence Record

Each extracted field should be represented as:

```text
field: container_no
raw_value: TRHU4217950
normalized_value: TRHU4217950
source_file: attachment-1.eml
source_location: nested body, forwarded Delivery Request paragraph 2
confidence: 0.98
used_for_write: false
```

Set `used_for_write` only after the user approves the structured preview and
the server accepts the source evidence ID. Attachment bytes and raw email
content stay local until encrypted object storage is configured; WMS receives
metadata, hashes, locations, and approved extracted fields rather than an
uncontrolled local path.
