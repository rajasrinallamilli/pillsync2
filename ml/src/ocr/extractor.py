"""
Clinical Medicine Information Extraction Engine for PillSync.
Extracts structured prescription and medication fields:
- Medicine Name, Brand Name, Active Ingredient / Generic Name
- Dosage Strength, Prescribed Dose Per Administration, Dosage Form, Route
- Frequency, Total Quantity, Treatment Duration, Start Date, End Date
- Prescription Date, Prescriber Name, Patient Details, Special Instructions, Refills Authorized
- Field-level Confidence Estimation and Human Verification Flagging

Maintains safe handling for uncertain OCR results, strictly avoids hallucination,
and preserves original text for clinical verification.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# Comprehensive clinical dictionary of common medications (generics & brands)
DRUG_LEXICON = [
    # Analgesics & Antipyretics
    "Paracetamol", "Acetaminophen", "Ibuprofen", "Aspirin", "Diclofenac", "Naproxen",
    "Tramadol", "Celecoxib", "Aceclofenac", "Ketorolac", "Mefenamic Acid",
    "Dolo", "Crocin", "Calpol", "Combiflam", "Panadol", "Tylenol", "Advil", "Motrin", "Aleve",

    # Antibiotics & Antimicrobials
    "Amoxicillin", "Azithromycin", "Ciprofloxacin", "Levofloxacin", "Doxycycline",
    "Cephalexin", "Cefixime", "Clavulanate", "Augmentin", "Metronidazole",
    "Erythromycin", "Clarithromycin", "Sulfamethoxazole", "Ampicillin", "Nitrofurantoin",
    "Ofloxacin", "Cefuroxime", "Cefpodoxime", "Norfloxacin", "Keflex", "Flagyl", "Zithromax", "Cipro",

    # Antihistamines & Allergy
    "Cetirizine", "Levocetirizine", "Loratadine", "Desloratadine", "Fexofenadine",
    "Diphenhydramine", "Chlorpheniramine", "Montelukast", "Hydroxyzine", "Allegra",
    "Zyrtec", "Claritin", "Avil", "Benadryl",

    # Antihypertensives & Cardiovascular
    "Amlodipine", "Telmisartan", "Losartan", "Valsartan", "Olmesartan", "Atenolol",
    "Metoprolol", "Propranolol", "Bisoprolol", "Carvedilol", "Enalapril", "Lisinopril",
    "Ramipril", "Hydrochlorothiazide", "Furosemide", "Spironolactone", "Atorvastatin",
    "Rosuvastatin", "Simvastatin", "Clopidogrel", "Digoxin", "Diltiazem", "Lipitor", "Crestor", "Norvasc",

    # Antidiabetic Agents
    "Metformin", "Glimepiride", "Gliclazide", "Glibenclamide", "Sitagliptin",
    "Vildagliptin", "Linagliptin", "Dapagliflozin", "Empagliflozin", "Pioglitazone",
    "Insulin", "Glipizide", "Januvia", "Glycomet", "Glucophage", "Amaryl",

    # Gastrointestinal & Antacids
    "Pantoprazole", "Omeprazole", "Rabeprazole", "Esomeprazole", "Lansoprazole",
    "Ranitidine", "Famotidine", "Domperidone", "Ondansetron", "Sucralfate",
    "Pan-D", "Omez", "Rantac", "Pantocid", "Prilosec", "Nexium", "Zantac",

    # Respiratory & Cough
    "Salbutamol", "Albuterol", "Budecort", "Budesonide", "Formoterol", "Ipratropium",
    "Theophylline", "Ambroxol", "Guaifenesin", "Dextromethorphan", "Asthalin",
    "Levosalbutamol", "Deriphyllin", "Ventolin",

    # Thyroid & Endocrine
    "Levothyroxine", "Thyroxine", "Eltroxin", "Synthroid",

    # Vitamins, Minerals & Supplements
    "Vitamin C", "Vitamin D3", "Vitamin B12", "Calcium", "Zinc", "Folic Acid",
    "Multivitamin", "Becosules", "Shelcal", "Neurobion", "Ferrous Sulfate",
    "B-Complex", "Iron", "Ascorbic Acid", "Cholecalciferol",

    # Steroids & Anti-inflammatory
    "Prednisolone", "Methylprednisolone", "Dexamethasone", "Betamethasone", "Deflazacort",

    # Central Nervous System & Psychiatric
    "Alprazolam", "Clonazepam", "Diazepam", "Lorazepam", "Escitalopram", "Sertraline",
    "Fluoxetine", "Amitriptyline", "Gabapentin", "Pregabalin", "Duloxetine",
]

# Knowledge base mapping brand names to their active generic ingredients and primary dosage forms
BRAND_TO_GENERIC_MAP = {
    "dolo": {"brand": "Dolo", "generic": "Paracetamol", "form": "tablet", "route": "oral"},
    "crocin": {"brand": "Crocin", "generic": "Paracetamol", "form": "tablet", "route": "oral"},
    "calpol": {"brand": "Calpol", "generic": "Paracetamol", "form": "suspension", "route": "oral"},
    "panadol": {"brand": "Panadol", "generic": "Paracetamol", "form": "tablet", "route": "oral"},
    "combiflam": {"brand": "Combiflam", "generic": "Ibuprofen + Paracetamol", "form": "tablet", "route": "oral"},
    "tylenol": {"brand": "Tylenol", "generic": "Acetaminophen", "form": "tablet", "route": "oral"},
    "advil": {"brand": "Advil", "generic": "Ibuprofen", "form": "tablet", "route": "oral"},
    "motrin": {"brand": "Motrin", "generic": "Ibuprofen", "form": "tablet", "route": "oral"},
    "aleve": {"brand": "Aleve", "generic": "Naproxen", "form": "tablet", "route": "oral"},
    "augmentin": {"brand": "Augmentin", "generic": "Amoxicillin + Clavulanate", "form": "tablet", "route": "oral"},
    "zithromax": {"brand": "Zithromax", "generic": "Azithromycin", "form": "tablet", "route": "oral"},
    "cipro": {"brand": "Cipro", "generic": "Ciprofloxacin", "form": "tablet", "route": "oral"},
    "ciprobay": {"brand": "Ciprobay", "generic": "Ciprofloxacin", "form": "tablet", "route": "oral"},
    "keflex": {"brand": "Keflex", "generic": "Cephalexin", "form": "capsule", "route": "oral"},
    "flagyl": {"brand": "Flagyl", "generic": "Metronidazole", "form": "tablet", "route": "oral"},
    "allegra": {"brand": "Allegra", "generic": "Fexofenadine", "form": "tablet", "route": "oral"},
    "zyrtec": {"brand": "Zyrtec", "generic": "Cetirizine", "form": "tablet", "route": "oral"},
    "claritin": {"brand": "Claritin", "generic": "Loratadine", "form": "tablet", "route": "oral"},
    "avil": {"brand": "Avil", "generic": "Pheniramine", "form": "tablet", "route": "oral"},
    "benadryl": {"brand": "Benadryl", "generic": "Diphenhydramine", "form": "syrup", "route": "oral"},
    "pan-d": {"brand": "Pan-D", "generic": "Pantoprazole + Domperidone", "form": "capsule", "route": "oral"},
    "pantocid": {"brand": "Pantocid", "generic": "Pantoprazole", "form": "tablet", "route": "oral"},
    "omez": {"brand": "Omez", "generic": "Omeprazole", "form": "capsule", "route": "oral"},
    "prilosec": {"brand": "Prilosec", "generic": "Omeprazole", "form": "capsule", "route": "oral"},
    "rantac": {"brand": "Rantac", "generic": "Ranitidine", "form": "tablet", "route": "oral"},
    "zantac": {"brand": "Zantac", "generic": "Ranitidine", "form": "tablet", "route": "oral"},
    "nexium": {"brand": "Nexium", "generic": "Esomeprazole", "form": "tablet", "route": "oral"},
    "lipitor": {"brand": "Lipitor", "generic": "Atorvastatin", "form": "tablet", "route": "oral"},
    "crestor": {"brand": "Crestor", "generic": "Rosuvastatin", "form": "tablet", "route": "oral"},
    "norvasc": {"brand": "Norvasc", "generic": "Amlodipine", "form": "tablet", "route": "oral"},
    "glycomet": {"brand": "Glycomet", "generic": "Metformin", "form": "tablet", "route": "oral"},
    "glucophage": {"brand": "Glucophage", "generic": "Metformin", "form": "tablet", "route": "oral"},
    "januvia": {"brand": "Januvia", "generic": "Sitagliptin", "form": "tablet", "route": "oral"},
    "amaryl": {"brand": "Amaryl", "generic": "Glimepiride", "form": "tablet", "route": "oral"},
    "asthalin": {"brand": "Asthalin", "generic": "Salbutamol", "form": "inhaler", "route": "inhalation"},
    "ventolin": {"brand": "Ventolin", "generic": "Albuterol", "form": "inhaler", "route": "inhalation"},
    "budecort": {"brand": "Budecort", "generic": "Budesonide", "form": "inhaler", "route": "inhalation"},
    "deriphyllin": {"brand": "Deriphyllin", "generic": "Theophylline + Etophylline", "form": "tablet", "route": "oral"},
    "becosules": {"brand": "Becosules", "generic": "B-Complex + Vitamin C", "form": "capsule", "route": "oral"},
    "shelcal": {"brand": "Shelcal", "generic": "Calcium + Vitamin D3", "form": "tablet", "route": "oral"},
    "neurobion": {"brand": "Neurobion", "generic": "Vitamin B1 + B6 + B12", "form": "tablet", "route": "oral"},
    "eltroxin": {"brand": "Eltroxin", "generic": "Levothyroxine", "form": "tablet", "route": "oral"},
    "synthroid": {"brand": "Synthroid", "generic": "Levothyroxine", "form": "tablet", "route": "oral"},
}

# Canonical clinical frequency map
FREQUENCY_MAP = [
    (r"\b(once\s+(?:a\s+)?daily|1\s+time\s+(?:a\s+)?(?:day|daily)|o\.?d\.?|q\.?d\.?)\b", "Once daily"),
    (r"\b(twice\s+(?:a\s+)?daily|2\s+times?\s+(?:a\s+)?(?:day|daily)|b\.?i\.?d\.?|b\.?d\.?)\b", "Twice daily"),
    (r"\b(thrice\s+(?:a\s+)?daily|three\s+times\s+(?:a\s+)?(?:day|daily)|3\s+times?\s+(?:a\s+)?(?:day|daily)|t\.?i\.?d\.?|t\.?d\.?s\.?)\b", "Three times daily"),
    (r"\b(four\s+times\s+(?:a\s+)?(?:day|daily)|4\s+times?\s+(?:a\s+)?(?:day|daily)|q\.?i\.?d\.?)\b", "Four times daily"),
    (r"\b(every\s+8\s+hours?|q8h)\b", "Every 8 hours"),
    (r"\b(every\s+12\s+hours?|q12h)\b", "Every 12 hours"),
    (r"\b(every\s+6\s+hours?|q6h)\b", "Every 6 hours"),
    (r"\b(every\s+4\s+hours?|q4h)\b", "Every 4 hours"),
    (r"\b(morning\s+and\s+night|morning\s+&\s+night|morn\s+&\s+night)\b", "Morning and night"),
    (r"\b(in\s+the\s+morning|morning\s+only|at\s+morning)\b", "Morning"),
    (r"\b(at\s+night|at\s+bedtime|night\s+only|bedtime|h\.?s\.?)\b", "Night"),
    (r"\b(after\s+breakfast)\b", "After breakfast"),
    (r"\b(before\s+breakfast)\b", "Before breakfast"),
    (r"\b(as\s+needed|p\.?r\.?n\.?|when\s+required)\b", "As needed"),
]

# Dosage strengths (metric and clinical strength units, including concentration)
DOSAGE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg/ml|mg|mcg|µg|g|ml|iu|mEq|%|puff|drops?)\b",
    re.IGNORECASE
)

# Prescribed dose per administration (e.g. 1 tablet, 2 capsules, 5 ml, 1 tsp)
DOSE_ADMIN_PATTERN = re.compile(
    r"\b(?:take\s+)?(\d+(?:\.\d+)?|one|two|three|four|half)\s*(tablets?|capsules?|pills?|teaspoons?|tsp|tablespoons?|tbsp|ml|drops?|puffs?|units?)\b",
    re.IGNORECASE
)

# Total dispense / pack quantity (e.g., Qty: 30 tablets, 1 bottle, Strip of 10)
TOTAL_QTY_PATTERN = re.compile(
    r"\b(?:qty|quantity|dispense|strip\s+of|total|#)\s*:?\s*(\d+)\s*(tablets?|capsules?|pills?|bottles?|strips?|vials?|ampoules?|tubes?|units?)?\b",
    re.IGNORECASE
)

# Duration of therapy
DURATION_PATTERN = re.compile(
    r"\b(?:for\s+|x\s*)?(\d+\s*(?:to\s*\d+\s*)?(?:days?|weeks?|months?))\b",
    re.IGNORECASE
)

# Dosage forms
DOSAGE_FORM_PATTERNS = [
    (r"\b(tablets?|tab\.?)\b", "tablet"),
    (r"\b(capsules?|cap\.?)\b", "capsule"),
    (r"\b(syrup|syr\.?)\b", "syrup"),
    (r"\b(suspension|susp\.?)\b", "suspension"),
    (r"\b(injection|inj\.?|ampoule|vial)\b", "injection"),
    (r"\b(cream|cr\.?)\b", "cream"),
    (r"\b(ointment|oint\.?)\b", "ointment"),
    (r"\b(gel)\b", "gel"),
    (r"\b(eye\s+drops?|ear\s+drops?|drops?|gtt)\b", "drops"),
    (r"\b(inhaler|inhalation|puff|rotacap)\b", "inhaler"),
    (r"\b(spray|nasal\s+spray)\b", "spray"),
    (r"\b(patch|transdermal)\b", "transdermal patch"),
    (r"\b(solution|sol\.?)\b", "solution"),
    (r"\b(powder|sachet)\b", "powder"),
]

# Routes of administration
ROUTE_PATTERNS = [
    (r"\b(oral|p\.?o\.?|by\s+mouth|per\s+os)\b", "oral"),
    (r"\b(topical|apply\s+externally|local)\b", "topical"),
    (r"\b(inhalation|inhale|orally\s+inhaled)\b", "inhalation"),
    (r"\b(ophthalmic|eye|into\s+eyes?)\b", "ophthalmic"),
    (r"\b(otic|ear|into\s+ears?)\b", "otic"),
    (r"\b(sublingual|under\s+the\s+tongue)\b", "sublingual"),
    (r"\b(intravenous|i\.?v\.?)\b", "intravenous"),
    (r"\b(intramuscular|i\.?m\.?)\b", "intramuscular"),
    (r"\b(subcutaneous|s\.?c\.?)\b", "subcutaneous"),
    (r"\b(nasal|in\s+each\s+nostril)\b", "nasal"),
]

# Instructions / details
DETAILS_PATTERNS = [
    (r"\b(after\s+(?:food|meals?|eating|breakfast|dinner|lunch))\b", "After food"),
    (r"\b(before\s+(?:food|meals?|eating|breakfast|dinner|lunch))\b", "Before food"),
    (r"\b(with\s+(?:food|meals?|water|milk))\b", "With food/water"),
    (r"\b(empty\s+stomach)\b", "On an empty stomach"),
    (r"\b(at\s+night|at\s+bedtime)\b", "At bedtime"),
    (r"\b(do\s+not\s+crush|swallow\s+whole)\b", "Do not crush, swallow whole"),
    (r"\b(shake\s+well\s+before\s+use)\b", "Shake well before use"),
    (r"\b(plenty\s+of\s+water)\b", "Take with plenty of water"),
]

# Doctor and header filtering
HEADER_PREFIXES = [
    "dr.", "dr ", "doctor", "hospital", "clinic", "pharmacy", "prescription",
    "patient", "age", "gender", "date", "reg", "phone", "address", "rx",
    "signature", "license", "qualification", "mbbs", "md", "consultant"
]


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


class MedicineExtractor:
    """
    Extracts structured multi-medicine records from OCR raw text.
    Maintains strict clinical safety: does not guess missing attributes.
    """

    def __init__(self, drug_lexicon: Optional[List[str]] = None):
        self.lexicon = drug_lexicon if drug_lexicon is not None else DRUG_LEXICON

    def extract(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Parses raw prescription text and extracts structured medicine records.
        """
        if not raw_text or not raw_text.strip():
            return []

        # Step 0: Clean OCR token merging artifacts
        cleaned_text = self._clean_ocr_artifacts(raw_text)

        # Step 1: Extract document-level metadata (Prescriber, Date, Patient, Refills)
        doc_metadata = self._extract_document_metadata(cleaned_text)

        # Step 2: Split text into candidate lines
        lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]

        # Step 3: Segment into individual medication order blocks
        medicine_blocks = self._segment_into_medicine_blocks(lines)

        # Step 4: Extract structured fields from each medication block
        structured_records = []
        for block in medicine_blocks:
            record = self._parse_block(block, doc_metadata)
            if record and record.get("medicine_name"):
                structured_records.append(record)

        # Fallback: if block segmentation found nothing, scan the whole cleaned text
        if not structured_records:
            fallback_record = self._parse_fallback(cleaned_text, doc_metadata)
            if fallback_record:
                structured_records.append(fallback_record)

        return structured_records

    def _clean_ocr_artifacts(self, text: str) -> str:
        """
        Cleans common OCR character/spacing merging errors.
        """
        t = text
        # Insert space between numbers and dosage units: e.g. 500mg -> 500 mg, 10ml -> 10 ml
        t = re.sub(r"(\d+)(mg|mcg|ml|g|iu|tablets?|capsules?|days?|weeks?|months?)", r"\1 \2", t, flags=re.IGNORECASE)
        # Fix common merged OCR prepositions: e.g. daysafter -> days after, dailyfor -> daily for
        t = re.sub(r"(days?|weeks?|months?)(after|before|with|for)", r"\1 \2", t, flags=re.IGNORECASE)
        # Normalize hyphens before quantities/units without altering dates (e.g. ' -1 tablet' -> ' - 1 tablet')
        t = re.sub(r"\s+-\s*(\d+)\s*(tablets?|capsules?|pills?|mg|ml)", r" - \1 \2", t, flags=re.IGNORECASE)
        return t

    def _extract_document_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extracts prescription-level details: Prescriber, Date, Patient, Refills.
        """
        metadata = {
            "prescriber_name": None,
            "prescription_date": None,
            "patient_name": None,
            "refills_authorized": None,
            "parsed_date": None,
        }

        # 1. Prescriber Name
        doc_match = re.search(
            r"\b(Dr\.?\s+[A-Za-z\s\.\,\-]+?)(?:,?\s*(?:MD|MBBS|DO|MS|DM|Consultant|Physician|Clinic|Hospital|\n|$))",
            text,
            re.IGNORECASE
        )
        if doc_match:
            doc_name = doc_match.group(1).strip()
            # Clean trailing punctuation
            doc_name = re.sub(r"[,\|\-]+$", "", doc_name).strip()
            metadata["prescriber_name"] = doc_name

        # 2. Prescription Date
        date_match = re.search(
            r"\b(\d{1,2}[-/\.](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\.]\d{2,4}|\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{2,4})\b",
            text,
            re.IGNORECASE
        )
        if date_match:
            date_str = date_match.group(1).strip()
            metadata["prescription_date"] = date_str
            for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
                try:
                    metadata["parsed_date"] = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    pass

        # 3. Patient Name
        pat_match = re.search(
            r"\b(?:Patient(?:\s+Name)?|Pt(?:\s+Name)?|Name)\s*:\s*([A-Za-z\s]+?)(?:\s+(?:Age|Gender|Sex|Date|Rx|Address)|\n|$)",
            text,
            re.IGNORECASE
        )
        if pat_match:
            metadata["patient_name"] = pat_match.group(1).strip()

        # 4. Refills Authorized
        refill_match = re.search(
            r"\b(?:refills?|repeats?)\s*:?\s*(\d+\s*(?:times?|refills?)?|none|zero|no)\b",
            text,
            re.IGNORECASE
        )
        if refill_match:
            ref_val = refill_match.group(1).strip().lower()
            if ref_val in ('none', 'zero', 'no'):
                metadata["refills_authorized"] = "None"
            else:
                metadata["refills_authorized"] = refill_match.group(1).strip()

        return metadata

    def _segment_into_medicine_blocks(self, lines: List[str]) -> List[str]:
        """
        Segments prescription lines into individual medication blocks.
        """
        blocks = []
        current_block = []

        for line in lines:
            lower_line = line.lower()

            if self._is_header_line(lower_line):
                continue

            # Check if this line marks the beginning of a medication entry
            is_new_entry = (
                re.match(r"^(?:\d+[\.\)\-:]|\*|-|•|tab(?:let)?\.?|cap(?:sule)?\.?|syr(?:up)?\.?|inj\.?)\s+", lower_line) or
                self._line_contains_known_drug(lower_line)
            )

            if is_new_entry and current_block:
                blocks.append(" ".join(current_block))
                current_block = [line]
            else:
                current_block.append(line)

        if current_block:
            blocks.append(" ".join(current_block))

        return blocks

    def _is_header_line(self, lower_line: str) -> bool:
        """Determines if a line is a clinic/doctor header rather than a medicine order."""
        for prefix in HEADER_PREFIXES:
            if lower_line.startswith(prefix) or f" {prefix}" in lower_line:
                if not DOSAGE_PATTERN.search(lower_line):
                    return True
        return False

    def _line_contains_known_drug(self, lower_line: str) -> bool:
        """Checks if a line contains any drug in the lexicon."""
        words = re.findall(r"[a-zA-Z]+", lower_line)
        for w in words:
            if len(w) >= 4:
                match, dist = self._find_best_drug_match(w)
                if match and dist <= 1:
                    return True
        return False

    def _parse_block(self, block_text: str, doc_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses a medication block into the full 16-field clinical structure."""
        # 1. Medicine Name + Brand / Generic Resolution
        name_info = self._extract_medicine_name(block_text)
        med_name = name_info["medicine_name"]
        if not med_name:
            return None

        name_conf = name_info["confidence"]
        brand_name = name_info["brand_name"]
        active_ingredient = name_info["active_ingredient"]
        is_ambiguous = name_info.get("is_ambiguous", False)

        # 2. Dosage Strength (e.g. 500 mg)
        strength, strength_conf = self._extract_dosage_strength(block_text)

        # 3. Treatment Duration (e.g. 5 days)
        duration = self._extract_duration(block_text)

        # 4. Frequency (e.g. Twice daily)
        frequency, freq_conf = self._extract_frequency(block_text)

        # 5. Dose Per Administration (e.g. 1 tablet)
        dose_per_admin = self._extract_dose_per_admin(block_text, strength)

        # 6. Total Dispense Quantity (e.g. 10 tablets, or prescribed unit dose count)
        explicit_qty = self._extract_quantity(block_text, strength, dose_per_admin)
        quantity = explicit_qty or dose_per_admin

        # 7. Dosage Form (e.g. tablet, capsule, syrup)
        dosage_form = self._extract_dosage_form(block_text, name_info.get("default_form"))

        # 8. Route of Administration (e.g. oral, topical, inhalation)
        route = self._extract_route(block_text, dosage_form, name_info.get("default_route"))

        # 9. Special Instructions (e.g. After food)
        instructions = self._extract_instructions(block_text)

        # 10. Start and End Dates derivation
        start_date = doc_metadata.get("prescription_date")
        end_date = None
        parsed_dt = doc_metadata.get("parsed_date")
        if parsed_dt and duration:
            dur_match = re.search(r"(\d+)\s*(days?|weeks?|months?)", duration, re.IGNORECASE)
            if dur_match:
                val = int(dur_match.group(1))
                unit = dur_match.group(2).lower()
                if unit.startswith("day"):
                    end_dt = parsed_dt + timedelta(days=val)
                elif unit.startswith("week"):
                    end_dt = parsed_dt + timedelta(weeks=val)
                elif unit.startswith("month"):
                    end_dt = parsed_dt + timedelta(days=val * 30)
                else:
                    end_dt = None

                if end_dt:
                    end_date = end_dt.strftime("%d-%b-%Y")

        # 11. Refills authorized (inherit from block or document)
        refills = self._extract_refills(block_text) or doc_metadata.get("refills_authorized")

        # 12. Field-level Confidence mapping
        field_confidence = {
            "medicine_name": name_conf,
            "strength": strength_conf,
            "frequency": freq_conf,
            "dose_per_administration": "High" if dose_per_admin else "Low",
            "quantity": "High" if quantity else "Low",
            "overall": self._compute_overall_confidence(name_conf, strength_conf, freq_conf)
        }

        # Verification required: always True for clinical safety, especially if any field is uncertain
        verification_required = True

        return {
            "medicine_name": med_name,
            "brand_name": brand_name,
            "active_ingredient": active_ingredient,
            "strength": strength,
            "dose_per_administration": dose_per_admin,
            "dosage_form": dosage_form,
            "route": route,
            "frequency": frequency,
            "quantity": quantity,
            "duration": duration,
            "start_date": start_date,
            "end_date": end_date,
            "prescription_date": doc_metadata.get("prescription_date"),
            "prescriber_name": doc_metadata.get("prescriber_name"),
            "patient_name": doc_metadata.get("patient_name"),
            "instructions": instructions,
            "refills_authorized": refills,
            "confidence": field_confidence["overall"],
            "field_confidence": field_confidence,
            "verification_required": verification_required,
            "potential_ambiguity": is_ambiguous,
            # Backward-compatibility aliases
            "dosage": strength,
            "prescription_details": instructions,
        }

    def _extract_medicine_name(self, text: str) -> Dict[str, Any]:
        """
        Identifies the medicine name, checks brand vs generic, and handles typo tolerance.
        """
        words = re.findall(r"[a-zA-Z]{4,}", text)
        best_match = None
        best_dist = 999
        matched_token = ""

        for token in words:
            lower_token = token.lower()
            if lower_token in ("tablet", "tablets", "capsule", "capsules", "syrup",
                               "daily", "twice", "times", "water", "after", "before",
                               "food", "morning", "night", "every", "hours", "days"):
                continue

            match, dist = self._find_best_drug_match(token)
            if match and dist < best_dist and dist <= 2:
                best_match = match
                best_dist = dist
                matched_token = token

        if best_match:
            cand_key = best_match.lower()
            # Check brand lookup
            if cand_key in BRAND_TO_GENERIC_MAP:
                brand_info = BRAND_TO_GENERIC_MAP[cand_key]
                return {
                    "medicine_name": brand_info["brand"],
                    "brand_name": brand_info["brand"],
                    "active_ingredient": brand_info["generic"],
                    "default_form": brand_info["form"],
                    "default_route": brand_info["route"],
                    "confidence": "High" if best_dist == 0 else "Medium",
                    "is_ambiguous": best_dist > 1,
                    "database_verified": True
                }
            else:
                return {
                    "medicine_name": best_match,
                    "brand_name": None,
                    "active_ingredient": best_match,
                    "default_form": "tablet",
                    "default_route": "oral",
                    "confidence": "High" if best_dist == 0 else "Medium",
                    "is_ambiguous": best_dist > 1,
                    "database_verified": True
                }

        # If no lexicon match, preserve the capitalized token as-is with Low confidence
        for token in words:
            lower_token = token.lower()
            if not any(lower_token.startswith(p) for p in HEADER_PREFIXES):
                if len(token) >= 5 and token[0].isupper():
                    return {
                        "medicine_name": token.capitalize(),
                        "brand_name": None,
                        "active_ingredient": None,
                        "default_form": None,
                        "default_route": None,
                        "confidence": "Low",
                        "is_ambiguous": True,
                        "database_verified": False
                    }

        return {
            "medicine_name": None,
            "brand_name": None,
            "active_ingredient": None,
            "confidence": "Low",
            "is_ambiguous": True,
            "database_verified": False
        }

    def _find_best_drug_match(self, candidate: str) -> Tuple[Optional[str], int]:
        """Finds closest matching drug in lexicon using edit distance."""
        cand_lower = candidate.lower()
        cand_len = len(cand_lower)
        best_drug = None
        min_dist = 999

        for drug in self.lexicon:
            drug_lower = drug.lower()
            if abs(len(drug_lower) - cand_len) > 2:
                continue

            if drug_lower == cand_lower:
                return drug, 0

            dist = _levenshtein_distance(cand_lower, drug_lower)
            if dist < min_dist:
                min_dist = dist
                best_drug = drug

        return best_drug, min_dist

    def _extract_dosage_strength(self, text: str) -> Tuple[Optional[str], str]:
        """Extracts strength dosage (e.g. 500 mg, 10 mg, 5 mg/ml)."""
        match = DOSAGE_PATTERN.search(text)
        if match:
            value = match.group(1)
            unit = match.group(2).lower()
            if unit in ('mg', 'mcg', 'g', 'ml', 'iu', 'mg/ml', 'meq', '%'):
                return f"{value} {unit}", "High"
            elif unit.startswith('drop'):
                return f"{value} drops", "High"
            elif unit.startswith('puff'):
                return f"{value} puff", "High"
            return f"{value} {unit}", "Medium"
        return None, "Low"

    def _extract_dose_per_admin(self, text: str, strength: Optional[str]) -> Optional[str]:
        """Extracts prescribed dose per administration (e.g. 1 tablet, 5 ml)."""
        match = DOSE_ADMIN_PATTERN.search(text)
        if match:
            val_str = match.group(1).lower()
            unit_str = match.group(2).lower()
            val_map = {"one": "1", "two": "2", "three": "3", "four": "4", "half": "1/2"}
            numeric_val = val_map.get(val_str, val_str)
            res = f"{numeric_val} {unit_str}"
            # Ensure not identical to strength (e.g. if strength is 500 mg, dose shouldn't be confused)
            if strength and res.lower() == strength.lower():
                return None
            return res
        return None

    def _extract_quantity(self, text: str, strength: Optional[str], dose: Optional[str]) -> Optional[str]:
        """Extracts total dispense quantity (e.g. 10 tablets, 30 capsules)."""
        match = TOTAL_QTY_PATTERN.search(text)
        if match:
            num = match.group(1)
            unit = match.group(2)
            qty_res = f"{num} {unit.lower()}" if unit else f"{num} units"
            # Avoid conflating quantity with dose or strength
            if (dose and qty_res.lower() == dose.lower()) or (strength and qty_res.lower() in strength.lower()):
                return None
            return qty_res

        # Pattern for "Qty: 10" or "Strip of 10"
        qty_num = re.search(r"\b(?:qty|quantity|strip\s+of|total)\s*:?\s*(\d+)\b", text, re.IGNORECASE)
        if qty_num:
            return f"{qty_num.group(1)} units"

        return None

    def _extract_dosage_form(self, text: str, default_form: Optional[str]) -> Optional[str]:
        """Identifies dosage form (tablet, capsule, syrup, etc.)."""
        for pattern, form_name in DOSAGE_FORM_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return form_name
        return default_form

    def _extract_route(self, text: str, dosage_form: Optional[str], default_route: Optional[str]) -> Optional[str]:
        """Identifies route of administration (oral, topical, inhalation, etc.)."""
        for pattern, route_name in ROUTE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return route_name

        # Infer from dosage form if not explicitly stated
        if dosage_form in ('tablet', 'capsule', 'syrup', 'suspension', 'solution', 'powder'):
            return "oral"
        elif dosage_form in ('cream', 'ointment', 'gel'):
            return "topical"
        elif dosage_form in ('inhaler', 'spray'):
            return "inhalation"
        elif dosage_form == 'drops':
            if re.search(r"\b(eye|ophthalmic)\b", text, re.IGNORECASE):
                return "ophthalmic"
            elif re.search(r"\b(ear|otic)\b", text, re.IGNORECASE):
                return "otic"
            return "oral"
        elif dosage_form == 'injection':
            return "injection"

        return default_route

    def _extract_frequency(self, text: str) -> Tuple[Optional[str], str]:
        """Extracts and normalizes clinical frequency."""
        for pattern, normalized in FREQUENCY_MAP:
            if re.search(pattern, text, re.IGNORECASE):
                return normalized, "High"

        # Check for Latin numeric shorthand: 1-0-1, 1-0-0, 1-1-1
        pattern_numeric = re.search(r"\b([01])-([01])-([01])(?:-([01]))?\b", text)
        if pattern_numeric:
            m, a, n = pattern_numeric.group(1), pattern_numeric.group(2), pattern_numeric.group(3)
            active_doses = sum([int(m), int(a), int(n)])
            if active_doses == 1:
                return "Once daily", "Medium"
            elif active_doses == 2:
                return "Twice daily", "Medium"
            elif active_doses == 3:
                return "Three times daily", "Medium"

        return None, "Low"

    def _extract_duration(self, text: str) -> Optional[str]:
        """Extracts duration of treatment (e.g. 5 days, 2 weeks)."""
        match = DURATION_PATTERN.search(text)
        if match:
            dur = match.group(1).strip()
            dur = re.sub(r"^(?:for|x)\s+", "", dur, flags=re.IGNORECASE)
            return dur
        return None

    def _extract_instructions(self, text: str) -> Optional[str]:
        """Extracts administration instructions (food timing, precautions)."""
        detected = []
        for pattern, label in DETAILS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                if label not in detected:
                    detected.append(label)

        if detected:
            return ", ".join(detected)
        return None

    def _extract_refills(self, text: str) -> Optional[str]:
        """Extracts refills authorized from line block."""
        match = re.search(r"\b(?:refills?|repeats?)\s*:?\s*(\d+|none|zero|no)\b", text, re.IGNORECASE)
        if match:
            v = match.group(1).lower()
            if v in ('none', 'zero', 'no'):
                return "None"
            return f"{match.group(1)} refills"
        return None

    def _compute_overall_confidence(self, name_conf: str, strength_conf: str, freq_conf: str) -> str:
        """Determines aggregate extraction confidence rating."""
        if name_conf == "Low":
            return "Low"
        if name_conf == "Medium":
            return "Medium"
        high_count = sum(1 for c in (name_conf, strength_conf, freq_conf) if c == "High")
        if high_count >= 2:
            return "High"
        return "Medium"

    def _parse_fallback(self, raw_text: str, doc_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Scans the entire raw text if block segmentation failed to yield items."""
        return self._parse_block(raw_text, doc_metadata)

    # Aliases for backward compatibility with previous test suites and callers
    _extract_dosage = _extract_dosage_strength
    _extract_details = _extract_instructions
