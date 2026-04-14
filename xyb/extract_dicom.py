"""Extract metadata from DICOM medical imaging files."""
from __future__ import annotations
from pathlib import Path


def extract_dicom(path: Path) -> dict:
    """Extract metadata from DICOM file. Returns extraction dict."""
    import pydicom
    ds = pydicom.dcmread(str(path), stop_before_pixels=True)

    study_date = str(getattr(ds, 'StudyDate', '') or '')
    modality = str(getattr(ds, 'Modality', '') or '')
    series_desc = str(getattr(ds, 'SeriesDescription', '') or '')
    institution = str(getattr(ds, 'InstitutionName', '') or '')
    manufacturer = str(getattr(ds, 'Manufacturer', '') or '')
    slice_thickness = str(getattr(ds, 'SliceThickness', '') or '')
    patient_name = str(getattr(ds, 'PatientName', '') or '')
    patient_id = str(getattr(ds, 'PatientID', '') or '')

    label_parts = [p for p in [modality, study_date, series_desc] if p]
    label = ' - '.join(label_parts) or path.name

    imaging_node = {
        'id': f'imaging_{path.stem}',
        'node_type': 'Imaging',
        'label': label,
        'source_file': str(path),
        'properties': {
            'modality': modality,
            'study_date': study_date,
            'series_description': series_desc,
            'slice_thickness': slice_thickness,
            'manufacturer': manufacturer,
            'institution': institution,
            'patient_name': patient_name,
            'patient_id': patient_id,
        }
    }

    edges = []
    if institution:
        hospital_id = f'hospital_{institution.replace(" ", "_").lower()}'
        hospital_node = {
            'id': hospital_id,
            'node_type': 'Hospital',
            'label': institution,
            'source_file': str(path),
        }
        edges.append({
            'source': imaging_node['id'],
            'target': hospital_id,
            'relation': 'performed_at',
            'confidence': 'EXTRACTED',
            'source_file': str(path),
        })
        return {
            'nodes': [imaging_node, hospital_node],
            'edges': edges,
            'timeline_events': _build_timeline(imaging_node, study_date, modality, series_desc),
            'source_file': str(path),
        }

    return {
        'nodes': [imaging_node],
        'edges': edges,
        'timeline_events': _build_timeline(imaging_node, study_date, modality, series_desc),
        'source_file': str(path),
    }


def _build_timeline(imaging_node: dict, study_date: str, modality: str, series_desc: str) -> list[dict]:
    """Build timeline events from DICOM metadata."""
    if not study_date:
        return []
    formatted_date = (
        f'{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}'
        if len(study_date) == 8 else study_date
    )
    desc = f'{modality}检查' if modality else '影像检查'
    if series_desc:
        desc += f': {series_desc}'
    return [{
        'date': formatted_date,
        'description': desc,
        'related_nodes': [imaging_node['id']],
    }]
