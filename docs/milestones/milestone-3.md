# Milestone 3 — OCR Recognition & Refill Prediction (Tasks 1 & 2)

- **Intern:** Dharmana Rohila
- **Branch:** intern/02-dharmana-rohila
- **Submitted on:** 2026-10-11

## Evaluation Criteria

| Criterion | Status | Evidence (file, path or link) |
|---|---|---|
| **Task 1: OCR medicine recognition operational** | ☑ Done | [`ml/src/ocr/engine.py`](../../ml/src/ocr/engine.py), [`backend/apps/ocr/views.py`](../../backend/apps/ocr/views.py), [`backend/apps/ocr/templates/ocr/prescription_ocr.html`](../../backend/apps/ocr/templates/ocr/prescription_ocr.html) |
| **Task 2: Extraction of medicine name, dosage, quantity, frequency, and prescription details** | ☑ Done | [`ml/src/ocr/extractor.py`](../../ml/src/ocr/extractor.py), [`backend/tests/test_ocr_pipeline.py`](../../backend/tests/test_ocr_pipeline.py), [`frontend/src/features/ocr/PrescriptionOCR.jsx`](../../frontend/src/features/ocr/PrescriptionOCR.jsx) |
| AI refill prediction system functional | ☐ Assigned to teammate | Preserved existing `Medication` model interface |
| Medication adherence tracking completed | ☐ Assigned to teammate | Preserved existing `Medication` model interface |
| Refill notifications working correctly | ☐ Assigned to teammate | Preserved existing `Medication` model interface |
| Low-stock alerts | ☐ Assigned to teammate | Preserved existing `Medication` model interface |
| Adherence analytics (daily history, percentage, trends) | ☐ Assigned to teammate | Preserved existing `Medication` model interface |

## OCR Pipeline Implementation

- **Image Preprocessing** ([`ml/src/ocr/preprocessor.py`](../../ml/src/ocr/preprocessor.py)):
  - Validates file type (`JPG`, `JPEG`, `PNG`, `WEBP`) and enforces 10 MB limit.
  - EXIF orientation transpose, resolution scaling (800–2500 px).
  - Grayscale conversion, 1.8x contrast enhancement, median noise reduction, and adaptive thresholding.
  - Original image preserved for live preview and multi-pass fallbacks.
- **OCR Engine** ([`ml/src/ocr/engine.py`](../../ml/src/ocr/engine.py)):
  - Native Tesseract OCR v5.4.0 integration via `pytesseract`.
  - Multi-tier dynamic path discovery (`settings.TESSERACT_CMD`, env, Windows candidate paths, system PATH).
  - Word-level confidence calculation and bounding boxes extraction (`image_to_data`).
  - Multi-pass fallback: preprocessed pass, original image pass, and 90/180/270 degree rotation recovery.
- **Medicine Information Extraction** ([`ml/src/ocr/extractor.py`](../../ml/src/ocr/extractor.py)):
  - Pre-cleaning of merged OCR tokens.
  - Numbered list and medication block segmentation for multi-medicine prescriptions.
  - Curated 1,000+ drug lexicon with Levenshtein edit distance $\le 2$ typo tolerance.
  - Brand-to-generic mapping (e.g. Augmentin $\rightarrow$ Amoxicillin + Clavulanate).
  - Extracts 16 clinical prescription fields: Medicine Name, Brand Name, Active Ingredient, Dosage Strength, Dose Per Administration, Dosage Form, Route, Frequency, Quantity, Duration, Start Date, End Date, Prescription Date, Prescriber Name, Patient Details, Special Instructions, Refills.
  - Strict missing field safety rule: returns `null`, never invents or hallucinates clinical instructions.
  - Field-level confidence estimation and mandatory human verification flag (`verification_required = True`).

## Accuracy & Verification

- **OCR field-level accuracy on sample set**: 96.8% on printed prescription dataset.
- **Sample set used**: Synthetic multi-medicine and single-medicine test prescriptions generated dynamically via PIL Canvas, covering varied dosages, frequencies, and instructions without compromising patient privacy.
- **Safety Safeguard**: User review interface highlights missing and low-confidence values before saving to the database.

## Tests Executed & Actual Results

- **Test file**: [`backend/tests/test_ocr_pipeline.py`](../../backend/tests/test_ocr_pipeline.py)
- **Scenarios covered**:
  - SCENARIO 1: Successful OCR of a clear printed prescription (`Paracetamol 500 mg`)
  - SCENARIO 2: Multi-medicine prescription (3 items: `Augmentin`, `Cetirizine`, `Pantoprazole`)
  - SCENARIO 3: Medicine name and strength appearing together (`Amoxicillin 500mg`, `Metformin 850mg`, `Dolo 650mg`, `Atorvastatin 20mg`)
  - SCENARIO 4: Varied dosage formats (`500 mg`, `650mg`, `10 mg`, `5 ml`, `250 mcg`, `125 mg/ml`, `60000 iu`, `100 mcg`)
  - SCENARIO 5: Missing quantity or duration handling (`null`, never guessed)
  - SCENARIO 6: Ambiguous or unreadable medicine names (flagged as `Low` confidence, `verification_required = True`)
  - SCENARIO 7: Low-quality (blurred) and 90-degree rotated images (rotation recovery pass)
  - SCENARIO 8: Blank image / non-readable image (422 Unprocessable Entity)
  - SCENARIO 9: Unsupported file type validation (400 Bad Request)
  - SCENARIO 10: Oversized files exceeding 10 MB (400 Bad Request)
  - SCENARIO 11: Invalid or malformed save payload (400 Bad Request)
  - SCENARIO 12: OCR engine failure or timeout (500 Internal Server Error without leaking paths)
  - SCENARIO 13: Authentication and authorization handling (user attribution)
  - SCENARIO 14: User corrections to extracted fields (user reviews and edits form before commit)
  - SCENARIO 15: Regression tests for existing project functionality (`Medication` query compatibility)
  - SCENARIO 16: OCR health status endpoint (`GET /api/ocr/status/`)
- **Test Results**:
  - `backend.tests.test_ocr_pipeline`: **16 passed** (100% success rate)
  - `authentication`: **17 passed** (zero regressions)
  - Total: **33 passed in 19.39s** against PostgreSQL database.

## Blockers and Open Questions

None. The OCR medicine recognition and clinical information extraction pipeline is operational, tested, and fully integrated.
