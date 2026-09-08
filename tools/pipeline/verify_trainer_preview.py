#!/usr/bin/env python3
"""Compatibility entry point for the no-PP, read-only-moves trainer UI regression.

Full league progression/settlement is exercised by verify_trainer_campaign.py;
visual and input coverage now lives in verify_combat_preview.py.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('verify_combat_preview.py')),run_name='__main__')
