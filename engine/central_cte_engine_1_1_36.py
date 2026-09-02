# -*- coding: utf-8 -*-
"""Ponto de entrada do Central CT-e / DACTE 2.7.0 RC26.6."""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_FILE = Path(__file__).resolve()
_ENGINE_DIR = _ENGINE_FILE.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from central_cte_modular.bootstrap.modular_runtime_loader import bootstrap_engine_facade
from central_cte_modular.rc26_6_runtime_patch import RC26_6_VERSION, install_rc26_6_runtime

CENTRAL_CTE_BOOTSTRAP = bootstrap_engine_facade(globals(), _ENGINE_FILE)
CENTRAL_CTE_RC26_6_STATE = install_rc26_6_runtime(globals(), CENTRAL_CTE_BOOTSTRAP)
APP_VERSION = RC26_6_VERSION

if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    CENTRAL_CTE_BOOTSTRAP.run_application()
