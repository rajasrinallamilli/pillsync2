from rest_framework import serializers
from .models import PrescriptionUpload
from backend.apps.medications.models import Medication


class BoundingBoxSerializer(serializers.Serializer):
    """
    Serializes individual recognized text word region with coordinates and confidence.
    """
    text = serializers.CharField()
    confidence = serializers.FloatField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()


class ExtractedMedicineSerializer(serializers.Serializer):
    """
    Serializes structured clinical medication fields extracted from prescription OCR.
    """
    medicine_name = serializers.CharField(max_length=255, required=True)
    brand_name = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    active_ingredient = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    strength = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    dose_per_administration = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    dosage_form = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    route = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    frequency = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    quantity = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    duration = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    start_date = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    end_date = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    prescription_date = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    prescriber_name = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    patient_name = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    instructions = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    refills_authorized = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    confidence = serializers.CharField(max_length=50, required=False, default='Medium')
    field_confidence = serializers.DictField(required=False)
    verification_required = serializers.BooleanField(required=False, default=True)
    potential_ambiguity = serializers.BooleanField(required=False, default=False)
    # Backward compatibility aliases
    dosage = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    prescription_details = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PrescriptionUploadResponseSerializer(serializers.Serializer):
    """
    Structured API response returned to client after prescription OCR processing.
    """
    success = serializers.BooleanField(default=True)
    upload_id = serializers.IntegerField(required=False, allow_null=True)
    image_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    raw_text = serializers.CharField(allow_blank=True)
    mean_confidence = serializers.FloatField(default=0.0)
    confidence_level = serializers.CharField(default='Medium')
    bounding_boxes = BoundingBoxSerializer(many=True, required=False)
    prescriber_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    prescription_date = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    patient_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    refills_authorized = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    medicines = ExtractedMedicineSerializer(many=True)
    verification_required = serializers.BooleanField(default=True)
    message = serializers.CharField()


class MedicationBatchSaveSerializer(serializers.Serializer):
    """
    Accepts reviewed/edited medicines from user and validates them for persistence.
    """
    medicines = ExtractedMedicineSerializer(many=True)

    def create(self, validated_data):
        user = self.context.get('user')
        if user and not user.is_authenticated:
            user = None

        created_meds = []
        for item in validated_data['medicines']:
            med_name = item['medicine_name']
            dosage_val = item.get('strength') or item.get('dosage')
            qty_val = item.get('quantity')
            freq_val = item.get('frequency')
            dur_val = item.get('duration')
            details_val = item.get('instructions') or item.get('prescription_details')
            conf_val = item.get('confidence', 'High')
            if isinstance(conf_val, dict):
                conf_val = conf_val.get('overall', 'High')

            med = Medication.objects.create(
                user=user,
                medicine_name=med_name,
                dosage=dosage_val,
                quantity=qty_val,
                frequency=freq_val,
                duration=dur_val,
                prescription_details=details_val,
                confidence=str(conf_val),
                source='OCR'
            )
            created_meds.append(med)
        return created_meds
