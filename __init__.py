# Copyright (C) 2026 J. Israel Villarreal B.
# SPDX-License-Identifier: GPL-2.0-or-later

from .plugin import CuadroDeConstruccionPlugin


def classFactory(iface):
    return CuadroDeConstruccionPlugin(iface)
