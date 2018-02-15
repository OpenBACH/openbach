#!/bin/bash
cd "$(dirname "$0")"
PYTHONPATH=../openbach-conductor/ ./openbach-backend.py test openbach_django.functional_tests
