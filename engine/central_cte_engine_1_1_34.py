# -*- coding: utf-8 -*-
"""Ponto de entrada mínimo do Central CT-e / DACTE 2.7.0 RC17.

O bootstrap é modular direto, sem coordenador de patches, descoberta de páginas
ou workers históricos. A interface Tk antiga permanece apenas como fallback de
recuperação acionado sob demanda.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_FILE = Path(__file__).resolve()
_ENGINE_DIR = _ENGINE_FILE.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from central_cte_modular.bootstrap.modular_runtime_loader import bootstrap_engine_facade

CENTRAL_CTE_BOOTSTRAP = bootstrap_engine_facade(globals(), _ENGINE_FILE)
from central_cte_modular.version import APP_VERSION

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    CENTRAL_CTE_BOOTSTRAP.run_application()
