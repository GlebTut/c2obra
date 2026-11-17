#!/usr/bin/env python3
"""C²oBra reports: read a CSS/JS template from a folder next to the sources and fill its
@@key@@ placeholders (used by report_html.py and merge_reports.py)."""

import os

SRC = os.path.dirname(os.path.abspath(__file__))


def read_asset(folder, name, **values):
    """Text of <src>/<folder>/<name> with every @@key@@ replaced by values[key]."""
    with open(os.path.join(SRC, folder, name), encoding="utf-8") as f:
        text = f.read().rstrip("\n")
    for key, value in values.items():
        text = text.replace("@@%s@@" % key, str(value))
    return text
