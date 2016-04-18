#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
rstats_reload.py - <+description+>
"""

import socket

cmd_reload = "4"
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("", 1111))
s.send(cmd_reload)
r = s.recv(9999)
s.close()
