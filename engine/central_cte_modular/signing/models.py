from __future__ import annotations

from dataclasses import dataclass

from .common import (STAMP_OFFICIAL_ROTATION_DEG, STAMP_OFFICIAL_X_MM, STAMP_OFFICIAL_Y_MM, STAMP_STANDARD_HEIGHT_MM, STAMP_STANDARD_WIDTH_MM)

@dataclass
class SignatureProfile:
    id: str
    name: str
    person_name: str
    role: str = ""
    title: str = "REDESPACHO"
    position: str = "official-stamp"
    active: bool = True
    created_at: str = ""
    updated_at: str = ""
    original_file: str = ""
    processed_file: str = ""
    original_sha256: str = ""
    threshold: int = 242
    stamp_size: str = "official"
    custom_x_mm: float = STAMP_OFFICIAL_X_MM
    custom_y_mm: float = STAMP_OFFICIAL_Y_MM
    custom_width_mm: float = STAMP_STANDARD_WIDTH_MM
    custom_height_mm: float = STAMP_STANDARD_HEIGHT_MM
    custom_rotation_deg: float = STAMP_OFFICIAL_ROTATION_DEG
    signature_scale_percent: float = 100.0
    signature_offset_x_mm: float = 0.0
    signature_offset_y_mm: float = 0.0
    last_used_at: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.processed_file)
