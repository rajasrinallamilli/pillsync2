"""
Comprehensive Production Test Suite for PillSync Milestone 2 / Tasks 1 & 2:
Production-Quality Medicine OCR and Prescription Information Extraction.

Covers all 15 required test scenarios:
- SCENARIO 1: Successful OCR of a clear printed prescription.
- SCENARIO 2: Successful extraction of multiple structured fields from recognized text.
- SCENARIO 3: Medicine name and strength appearing together.
- SCENARIO 4: Different dosage strengths and units.
- SCENARIO 5: Missing quantity or duration handling (null, no guessing).
- SCENARIO 6: Ambiguous or unreadable medicine names.
- SCENARIO 7: Low-quality or rotated images.
- SCENARIO 8: Empty or non-readable images.
- SCENARIO 9: Unsupported file formats.
- SCENARIO 10: Oversized files.
- SCENARIO 11: Invalid or malformed extraction output.
- SCENARIO 12: OCR engine failure or timeout.
- SCENARIO 13: Authentication and authorization handling.
- SCENARIO 14: User corrections to extracted fields.
- SCENARIO 15: Regression tests for existing project functionality.
- ADDITIONAL: OCR health status endpoint check.
"""

import io
import os
from unittest.mock import patch
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from PIL import Image, ImageDraw, ImageFilter

from ml.src.ocr.preprocessor import ImagePreprocessor, ImageValidationError
from ml.src.ocr.engine import OCREngine, OCREngineError
from ml.src.ocr.extractor import MedicineExtractor
from backend.apps.medications.models import Medication
from backend.apps.ocr.models import PrescriptionUpload


def create_test_image(lines, size=(850, 260), blur=False, blank=False, rotate_angle=0):
    """Helper to synthesize test prescription images for real OCR execution."""
    img = Image.new('RGB', size, color=(255, 255, 255))
    if not blank:
        draw = ImageDraw.Draw(img)
        draw.text((20, 15), "Dr. Arthur Vance, MD - Metro Health Center", fill=(0, 0, 0))
        draw.text((20, 40), "Date: 28-Sep-2026 | Rx:", fill=(0, 0, 0))
        y = 75
        for line in lines:
            draw.text((20, y), line, fill=(0, 0, 0))
            y += 45

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    if rotate_angle:
        img = img.rotate(rotate_angle, expand=True)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


class ProductionOCRPipelineTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.preprocessor = ImagePreprocessor()
        self.engine = OCREngine()
        self.extractor = MedicineExtractor()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="testpatient@example.com",
            email="testpatient@example.com",
            password="dummy-password-123"
        )

    # --------------------------------------------------------------------------
    # SCENARIO 1: Successful OCR of a clear printed prescription
    # --------------------------------------------------------------------------
    def test_01_successful_ocr_clear_printed_prescription(self):
        """SCENARIO 1: Verifies real OCR inference on clear image, returning raw text, conf, boxes."""
        image_bytes = create_test_image([
            "1. Paracetamol 500 mg - 1 tablet twice daily for 5 days after food"
        ])
        uploaded = SimpleUploadedFile("clear_rx.png", image_bytes, content_type="image/png")
        response = self.client.post('/api/ocr/extract/', {'prescription_image': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn("Paracetamol", data['raw_text'])
        self.assertGreater(data['mean_confidence'], 50.0)
        self.assertIn(data['confidence_level'], ['High', 'Medium'])
        self.assertTrue(len(data['bounding_boxes']) > 0)
        self.assertTrue(len(data['medicines']) >= 1)

        first_med = data['medicines'][0]
        self.assertEqual(first_med['medicine_name'], "Paracetamol")
        self.assertEqual(first_med['strength'], "500 mg")
        self.assertEqual(first_med['frequency'], "Twice daily")

    # --------------------------------------------------------------------------
    # SCENARIO 2: Successful extraction of multiple structured fields
    # --------------------------------------------------------------------------
    def test_02_multiple_medicines_and_all_fields(self):
        """SCENARIO 2: Verifies extraction of all 16 clinical prescription fields across multiple items."""
        raw_text = (
            "Metro Health Clinic\n"
            "Dr. Arthur Vance, MD\n"
            "Date: 28-Sep-2026\n"
            "Patient: John Doe\n"
            "Rx:\n"
            "1. Augmentin 500 mg - 1 tablet twice daily for 5 days after food Qty: 10 tablets\n"
            "2. Cetirizine 10 mg - 1 tablet once daily at night for 10 days\n"
            "3. Pantoprazole 40 mg - 1 tablet once daily before food for 14 days\n"
            "Refills: 2\n"
        )
        meds = self.extractor.extract(raw_text)
        self.assertEqual(len(meds), 3)

        # Medicine 1: Augmentin (Brand resolved to active ingredient)
        med1 = meds[0]
        self.assertEqual(med1['medicine_name'], "Augmentin")
        self.assertEqual(med1['brand_name'], "Augmentin")
        self.assertEqual(med1['active_ingredient'], "Amoxicillin + Clavulanate")
        self.assertEqual(med1['strength'], "500 mg")
        self.assertEqual(med1['dose_per_administration'], "1 tablet")
        self.assertEqual(med1['dosage_form'], "tablet")
        self.assertEqual(med1['route'], "oral")
        self.assertEqual(med1['frequency'], "Twice daily")
        self.assertEqual(med1['duration'], "5 days")
        self.assertEqual(med1['start_date'], "28-Sep-2026")
        self.assertEqual(med1['end_date'], "03-Oct-2026")
        self.assertEqual(med1['prescriber_name'], "Dr. Arthur Vance")
        self.assertIn("After food", med1['instructions'])
        self.assertIn("2", med1['refills_authorized'])
        self.assertTrue(med1['verification_required'])

        # Medicine 2: Cetirizine
        med2 = meds[1]
        self.assertEqual(med2['medicine_name'], "Cetirizine")
        self.assertEqual(med2['strength'], "10 mg")
        self.assertEqual(med2['frequency'], "Once daily")
        self.assertEqual(med2['duration'], "10 days")

        # Medicine 3: Pantoprazole
        med3 = meds[2]
        self.assertEqual(med3['medicine_name'], "Pantoprazole")
        self.assertEqual(med3['strength'], "40 mg")
        self.assertEqual(med3['frequency'], "Once daily")
        self.assertIn("Before food", med3['instructions'])

    # --------------------------------------------------------------------------
    # SCENARIO 3: Medicine name and strength appearing together
    # --------------------------------------------------------------------------
    def test_03_medicine_name_and_strength_together(self):
        """SCENARIO 3: Correctly parses concatenated/adjacent medicine name and strength tokens."""
        test_cases = [
            ("Amoxicillin 500mg twice daily", "Amoxicillin", "500 mg"),
            ("Metformin 850mg once daily", "Metformin", "850 mg"),
            ("Dolo 650mg three times daily", "Dolo", "650 mg"),
            ("Atorvastatin 20mg at bedtime", "Atorvastatin", "20 mg"),
            ("Cetirizine 10mg once daily", "Cetirizine", "10 mg"),
        ]
        for text, expected_name, expected_strength in test_cases:
            with self.subTest(text=text):
                meds = self.extractor.extract(text)
                self.assertTrue(len(meds) >= 1)
                self.assertEqual(meds[0]['medicine_name'], expected_name)
                self.assertEqual(meds[0]['strength'], expected_strength)

    # --------------------------------------------------------------------------
    # SCENARIO 4: Different dosage strengths and units
    # --------------------------------------------------------------------------
    def test_04_different_dosage_strengths_and_units(self):
        """SCENARIO 4: Verifies varied clinical units: mg, mcg, g, ml, mg/ml, iu, puff, drops."""
        test_cases = [
            ("Paracetamol 500 mg once daily", "500 mg"),
            ("Dolo 650mg twice daily", "650 mg"),
            ("Cetirizine 10 mg at night", "10 mg"),
            ("Ambroxol 5 ml twice daily", "5 ml"),
            ("Levothyroxine 250 mcg in the morning", "250 mcg"),
            ("Amoxicillin 125 mg/ml suspension", "125 mg/ml"),
            ("Vitamin D3 60000 iu weekly", "60000 iu"),
            ("Asthalin 100 mcg 2 puff twice daily", "100 mcg"),
        ]
        for text, expected_dosage in test_cases:
            with self.subTest(text=text):
                dosage, conf = self.extractor._extract_dosage_strength(text)
                self.assertEqual(dosage, expected_dosage)
                self.assertIn(conf, ("High", "Medium"))

    # --------------------------------------------------------------------------
    # SCENARIO 5: Missing quantity or duration handling
    # --------------------------------------------------------------------------
    def test_05_missing_quantity_or_duration(self):
        """SCENARIO 5: Missing quantity or duration are set to None, never hallucinated."""
        # Case A: Missing quantity
        text_no_qty = "1. Paracetamol 500 mg twice daily for 5 days"
        meds_no_qty = self.extractor.extract(text_no_qty)
        self.assertEqual(len(meds_no_qty), 1)
        self.assertIsNone(meds_no_qty[0]['quantity'])
        self.assertEqual(meds_no_qty[0]['duration'], "5 days")

        # Case B: Missing duration
        text_no_dur = "1. Azithromycin 500 mg 1 tablet once daily Qty: 6 tablets"
        meds_no_dur = self.extractor.extract(text_no_dur)
        self.assertEqual(len(meds_no_dur), 1)
        self.assertIsNone(meds_no_dur[0]['duration'])
        self.assertEqual(meds_no_dur[0]['quantity'], "6 tablets")

        # Case C: Missing both quantity and duration
        text_bare = "1. Pantoprazole 40 mg once daily before food"
        meds_bare = self.extractor.extract(text_bare)
        self.assertEqual(len(meds_bare), 1)
        self.assertIsNone(meds_bare[0]['quantity'])
        self.assertIsNone(meds_bare[0]['duration'])
        self.assertEqual(meds_bare[0]['strength'], "40 mg")

    # --------------------------------------------------------------------------
    # SCENARIO 6: Ambiguous or unreadable medicine names
    # --------------------------------------------------------------------------
    def test_06_ambiguous_or_unreadable_medicine_names(self):
        """SCENARIO 6: Ambiguous names are flagged with verification_required=True and low confidence."""
        # Unrecognized drug name
        raw_text = "Rx: Tab UnknownMedDrug 250 mg once daily for 5 days"
        meds = self.extractor.extract(raw_text)
        self.assertEqual(len(meds), 1)
        med = meds[0]
        self.assertEqual(med['medicine_name'], "Unknownmeddrug")
        self.assertEqual(med['confidence'], "Low")
        self.assertTrue(med['potential_ambiguity'])
        self.assertTrue(med['verification_required'])

    # --------------------------------------------------------------------------
    # SCENARIO 7: Low-quality or rotated images
    # --------------------------------------------------------------------------
    def test_07_low_quality_and_rotated_images(self):
        """SCENARIO 7: Blurred images handled gracefully; rotated images recovered via orientation pass."""
        # 1. Blurred image
        blurred_png = create_test_image(["Paracetamol 500 mg twice daily"], blur=True)
        uploaded_blur = SimpleUploadedFile("blurred.png", blurred_png, content_type="image/png")
        res_blur = self.client.post('/api/ocr/extract/', {'prescription_image': uploaded_blur}, format='multipart')
        self.assertIn(res_blur.status_code, [status.HTTP_200_OK, status.HTTP_422_UNPROCESSABLE_ENTITY])

        # 2. 90-degree rotated image recovery
        rot_png = create_test_image(["Amoxicillin 500 mg twice daily for 7 days"], rotate_angle=90)
        uploaded_rot = SimpleUploadedFile("rotated.png", rot_png, content_type="image/png")
        res_rot = self.client.post('/api/ocr/extract/', {'prescription_image': uploaded_rot}, format='multipart')
        self.assertEqual(res_rot.status_code, status.HTTP_200_OK)
        data_rot = res_rot.json()
        self.assertTrue(data_rot['success'])
        self.assertIn("Amoxicillin", data_rot['raw_text'])

    # --------------------------------------------------------------------------
    # SCENARIO 8: Empty or non-readable images
    # --------------------------------------------------------------------------
    def test_08_empty_or_non_readable_image(self):
        """SCENARIO 8: Blank image returns 422 Unprocessable Entity with meaningful error."""
        blank_png = create_test_image([], blank=True)
        uploaded = SimpleUploadedFile("blank.png", blank_png, content_type="image/png")
        response = self.client.post('/api/ocr/extract/', {'prescription_image': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Unable to detect any readable text", data['error'])
        self.assertEqual(len(data['medicines']), 0)

    # --------------------------------------------------------------------------
    # SCENARIO 9: Unsupported file formats
    # --------------------------------------------------------------------------
    def test_09_unsupported_file_format(self):
        """SCENARIO 9: Rejects non-image files (.exe, .txt) with HTTP 400 Bad Request."""
        bad_file = SimpleUploadedFile("payload.exe", b"MZ\x90\x00malicious", content_type="application/octet-stream")
        response = self.client.post('/api/ocr/extract/', {'prescription_image': bad_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Unsupported file type", data['error'])

    # --------------------------------------------------------------------------
    # SCENARIO 10: Oversized files
    # --------------------------------------------------------------------------
    def test_10_oversized_file_validation(self):
        """SCENARIO 10: Files exceeding 10 MB limit are rejected with HTTP 400 Bad Request."""
        # 11 MB dummy content with .png extension
        oversized_data = b"x" * (11 * 1024 * 1024)
        oversized_file = SimpleUploadedFile("huge_scan.png", oversized_data, content_type="image/png")
        response = self.client.post('/api/ocr/extract/', {'prescription_image': oversized_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("exceeds maximum allowed limit", data['error'])

    # --------------------------------------------------------------------------
    # SCENARIO 11: Invalid or malformed extraction output / save payload
    # --------------------------------------------------------------------------
    def test_11_invalid_or_malformed_save_payload(self):
        """SCENARIO 11: Rejects empty or malformed medication payloads with HTTP 400."""
        # Empty payload
        res_empty = self.client.post('/api/ocr/save/', {}, format='json')
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing required medicine_name
        res_malformed = self.client.post('/api/ocr/save/', {'medicines': [{'dosage': '500 mg'}]}, format='json')
        self.assertEqual(res_malformed.status_code, status.HTTP_400_BAD_REQUEST)

    # --------------------------------------------------------------------------
    # SCENARIO 12: OCR engine failure or timeout
    # --------------------------------------------------------------------------
    def test_12_ocr_engine_failure_handling(self):
        """SCENARIO 12: Handles unexpected OCR failure gracefully with HTTP 500 without leaking paths."""
        image_bytes = create_test_image(["Paracetamol 500 mg"])
        uploaded = SimpleUploadedFile("test.png", image_bytes, content_type="image/png")

        with patch.object(OCREngine, 'extract_text', side_effect=OCREngineError("Engine timeout")):
            response = self.client.post('/api/ocr/extract/', {'prescription_image': uploaded}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("OCR processing failed", data['error'])

    # --------------------------------------------------------------------------
    # SCENARIO 13: Authentication and authorization handling
    # --------------------------------------------------------------------------
    def test_13_authentication_and_user_attribution(self):
        """SCENARIO 13: When user is authenticated, medications and audit records are bound to user."""
        self.client.force_authenticate(user=self.user)
        save_payload = {
            'medicines': [
                {
                    'medicine_name': 'Amlodipine',
                    'strength': '5 mg',
                    'frequency': 'Once daily',
                    'duration': '30 days'
                }
            ]
        }
        res = self.client.post('/api/ocr/save/', save_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        med = Medication.objects.filter(medicine_name='Amlodipine').first()
        self.assertIsNotNone(med)
        self.assertEqual(med.user, self.user)
        self.assertEqual(med.dosage, '5 mg')

    # --------------------------------------------------------------------------
    # SCENARIO 14: User corrections to extracted fields
    # --------------------------------------------------------------------------
    def test_14_user_corrections_workflow(self):
        """SCENARIO 14: Simulates user reviewing OCR output, editing values, and saving corrections."""
        # 1. OCR outputs initial extracted item
        raw_text = "1. Paracetamol 500 mg - 1 tablet twice daily for 5 days"
        extracted = self.extractor.extract(raw_text)[0]

        # 2. User edits dosage from 500 mg to 650 mg and frequency to Thrice daily
        user_corrected_meds = [
            {
                'medicine_name': extracted['medicine_name'],
                'strength': '650 mg',
                'dosage': '650 mg',
                'dose_per_administration': extracted['dose_per_administration'],
                'quantity': '15 tablets',
                'frequency': 'Three times daily',
                'duration': '5 days',
                'instructions': 'After meals with water',
                'confidence': 'High'
            }
        ]

        # 3. User submits corrected form
        res = self.client.post('/api/ocr/save/', {'medicines': user_corrected_meds}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 4. Database confirms user-corrected values are saved
        saved = Medication.objects.filter(medicine_name='Paracetamol', dosage='650 mg').first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.frequency, 'Three times daily')
        self.assertEqual(saved.quantity, '15 tablets')
        self.assertEqual(saved.prescription_details, 'After meals with water')

    # --------------------------------------------------------------------------
    # SCENARIO 15: Regression tests for existing project functionality
    # --------------------------------------------------------------------------
    def test_15_regression_for_existing_milestone_queries(self):
        """SCENARIO 15: Confirms Medication schema supports downstream milestone queries."""
        med = Medication.objects.create(
            user=self.user,
            medicine_name="Metformin",
            dosage="500 mg",
            quantity="60 tablets",
            frequency="Twice daily",
            duration="30 days",
            source="OCR"
        )
        # Downstream query simulation: Refill prediction and adherence tracking
        active_meds = Medication.objects.filter(user=self.user, medicine_name="Metformin")
        self.assertEqual(active_meds.count(), 1)
        self.assertEqual(active_meds.first().dosage, "500 mg")
        self.assertEqual(active_meds.first().source, "OCR")

    # --------------------------------------------------------------------------
    # OCR Health Status Check
    # --------------------------------------------------------------------------
    def test_16_ocr_status_health_check(self):
        """Verifies GET /api/ocr/status/ reports operational status and Tesseract engine version."""
        res = self.client.get('/api/ocr/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], 'operational')
        self.assertTrue(data['tesseract_installed'])
        self.assertIn("5.4", data['tesseract_version'])
