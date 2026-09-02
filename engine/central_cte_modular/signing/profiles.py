from __future__ import annotations

import hashlib
import html
import json
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .common import (MAX_PERSON_NAME, MAX_PROFILE_NAME, MAX_TITLE, PROFILE_FILE, VERSION, _atomic_write_text,
                     STAMP_MIN_WIDTH_MM, STAMP_OFFICIAL_ROTATION_DEG, STAMP_OFFICIAL_X_MM,
                     STAMP_STANDARD_HEIGHT_MM, STAMP_STANDARD_WIDTH_MM, SIGNATURE_SCALE_MIN_PERCENT,
                     SIGNATURE_SCALE_MAX_PERCENT, SIGNATURE_OFFSET_LIMIT_MM)
from .models import SignatureProfile

class SignatureProfileStore:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.root = self.runtime_dir / "sessoes" / "assinaturas"
        self.originals = self.root / "originais"
        self.processed = self.root / "tratadas"
        self.sheets = self.root / "folhas_cadastro"
        self.logs = self.runtime_dir / "logs"
        for folder in (self.root, self.originals, self.processed, self.sheets, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        self.path = self.root / PROFILE_FILE

    def load(self) -> list[SignatureProfile]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("profiles", raw if isinstance(raw, list) else [])
            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                allowed = {field for field in SignatureProfile.__dataclass_fields__}
                data = {key: value for key, value in item.items() if key in allowed}
                profile = SignatureProfile(**data)
                if float(getattr(profile, "custom_width_mm", 0.0) or 0.0) < STAMP_MIN_WIDTH_MM:
                    profile.custom_width_mm = STAMP_STANDARD_WIDTH_MM
                    profile.custom_height_mm = STAMP_STANDARD_HEIGHT_MM
                    if float(getattr(profile, "custom_x_mm", 0.0) or 0.0) > 125.0:
                        profile.custom_x_mm = STAMP_OFFICIAL_X_MM
                    if abs(float(getattr(profile, "custom_y_mm", 0.0) or 0.0) - 199.0) < 0.01:
                        profile.custom_y_mm = STAMP_OFFICIAL_Y_MM
                    if abs(float(getattr(profile, "custom_rotation_deg", 0.0) or 0.0) + 15.0) < 0.01:
                        profile.custom_rotation_deg = STAMP_OFFICIAL_ROTATION_DEG
                if str(getattr(profile, "stamp_size", "") or "").lower() in {"small", "medium", "large", ""}:
                    profile.stamp_size = "official"
                profile.signature_scale_percent = max(SIGNATURE_SCALE_MIN_PERCENT, min(SIGNATURE_SCALE_MAX_PERCENT, float(getattr(profile, "signature_scale_percent", 100.0) or 100.0)))
                profile.signature_offset_x_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, float(getattr(profile, "signature_offset_x_mm", 0.0) or 0.0)))
                profile.signature_offset_y_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, float(getattr(profile, "signature_offset_y_mm", 0.0) or 0.0)))
                result.append(profile)
            return result
        except Exception:
            self._log_error("Falha ao ler perfis de assinatura", traceback.format_exc())
            return []

    def save(self, profiles: Iterable[SignatureProfile]) -> None:
        payload = {
            "version": VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "profiles": [asdict(profile) for profile in profiles],
        }
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def get(self, profile_id: str) -> Optional[SignatureProfile]:
        for profile in self.load():
            if profile.id == profile_id:
                return profile
        return None

    def upsert(self, profile: SignatureProfile) -> SignatureProfile:
        profiles = self.load()
        now = datetime.now().isoformat(timespec="seconds")
        if not profile.created_at:
            profile.created_at = now
        profile.updated_at = now
        replaced = False
        for index, current in enumerate(profiles):
            if current.id == profile.id:
                profiles[index] = profile
                replaced = True
                break
        if not replaced:
            profiles.append(profile)
        self.save(profiles)
        return profile

    def delete(self, profile_id: str) -> bool:
        profiles = self.load()
        target = next((profile for profile in profiles if profile.id == profile_id), None)
        if target is None:
            return False
        remaining = [profile for profile in profiles if profile.id != profile_id]
        self.save(remaining)
        for value in (target.original_file, target.processed_file):
            if not value:
                continue
            try:
                path = Path(value)
                if path.exists() and self.root in path.resolve().parents:
                    path.unlink()
            except Exception:
                pass
        return True

    def create_profile(self, name: str, person_name: str, role: str, title: str, position: str) -> SignatureProfile:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        token = hashlib.sha1(f"{name}|{person_name}|{time.time_ns()}".encode("utf-8")).hexdigest()[:7].upper()
        profile_id = f"ASS-{stamp[-8:]}-{token}"
        return self.upsert(SignatureProfile(
            id=profile_id,
            name=str(name or "Assinatura").strip()[:MAX_PROFILE_NAME],
            person_name=str(person_name or "").strip()[:MAX_PERSON_NAME],
            role=str(role or "").strip()[:MAX_PERSON_NAME],
            title=str(title or "REDESPACHO").strip()[:MAX_TITLE],
            position=position or "official-stamp",
        ))

    def _log_error(self, context: str, details: str) -> None:
        try:
            path = self.logs / f"assinatura_pdf_erros_{datetime.now():%Y%m%d}.txt"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{datetime.now():%d/%m/%Y %H:%M:%S}] {context}\n{details}\n")
        except Exception:
            pass

def registration_sheet_html(profile: SignatureProfile) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Cadastro de assinatura {html.escape(profile.id)}</title>
<style>
@page {{ size:A4 portrait; margin:12mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial,sans-serif; color:#111; }}
.sheet {{ width:186mm; min-height:273mm; padding:8mm; border:1px solid #bbb; }}
h1 {{ font-size:20px; margin:0 0 8mm; text-align:center; }}
.meta {{ display:grid; grid-template-columns:34mm 1fr; gap:3mm 4mm; font-size:12px; margin-bottom:9mm; }}
.meta b {{ text-transform:uppercase; font-size:10px; }}
.instructions {{ font-size:13px; line-height:1.45; padding:5mm; background:#f5f7fa; border-left:4px solid #0b4f9f; margin-bottom:10mm; }}
.signature-frame {{ position:relative; width:150mm; height:58mm; margin:0 auto; border:2px solid #111; background:#fff; }}
.corner {{ position:absolute; width:12mm; height:12mm; }}
.c1 {{ left:-2px; top:-2px; border-left:6px solid #111; border-top:6px solid #111; }}
.c2 {{ right:-2px; top:-2px; border-right:6px solid #111; border-top:6px solid #111; }}
.c3 {{ left:-2px; bottom:-2px; border-left:6px solid #111; border-bottom:6px solid #111; }}
.c4 {{ right:-2px; bottom:-2px; border-right:6px solid #111; border-bottom:6px solid #111; }}
.frame-label {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#d6d6d6; font-size:21px; letter-spacing:2px; font-weight:bold; }}
.code {{ margin-top:7mm; text-align:center; font:700 13px monospace; letter-spacing:1px; }}
.warning {{ margin-top:12mm; font-size:11px; line-height:1.4; }}
</style></head><body><div class="sheet">
<h1>CADASTRO DE ASSINATURA - CENTRAL CT-e</h1>
<div class="meta">
<b>Perfil</b><span>{html.escape(profile.name)}</span>
<b>Responsável</b><span>{html.escape(profile.person_name)}</span>
<b>Cargo / setor</b><span>{html.escape(profile.role or '-')}</span>
<b>Título no documento</b><span>{html.escape(profile.title or '-')}</span>
</div>
<div class="instructions"><b>Como preencher:</b> imprima esta folha em tamanho A4, assine dentro do quadro usando caneta azul ou preta e depois digitalize a página inteira em PDF, JPG ou PNG. Não encoste a assinatura nas bordas.</div>
<div class="signature-frame" data-registration-box="1">
<div class="corner c1"></div><div class="corner c2"></div><div class="corner c3"></div><div class="corner c4"></div>
</div>
<div class="code">CÓDIGO DO CADASTRO: {html.escape(profile.id)}</div>
<div class="warning">A imagem tratada será utilizada somente na representação HTML/PDF do DACTE. O XML fiscal autorizado não será modificado.</div>
</div></body></html>"""
