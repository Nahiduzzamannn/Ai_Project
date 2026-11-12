# Scan questions: queued OCR flow

Upload a PDF or image in **Scan questions**. The page returns immediately with
an import ID, then shows `queued` or `processing` and the number of pages
completed. It requests the import status every **2 seconds** while the job is
active. You can refresh the browser or open a previous scan; the job continues
on the backend.

When OCR completes, the existing review screen shows proposed questions,
options, the original file, and the full extracted text. Correct questionable
Bangla, English, math, and MCQ content before saving it to the question bank.
Each page indicates whether the Bangla Paddle model or Tesseract produced its
text. If both engines fail, the import shows an error.

Every PDF page is OCR'd, including PDFs with embedded text. The old
`force_ocr` checkbox is removed. Other pages of the application keep their
existing behavior. The frontend still starts with `npm.cmd run dev` from this
folder on Windows. See `Backend/backend/SCAN_OCR_SETUP.md` for the backend,
model, database, and worker commands.
