#!/usr/bin/env python
"""Ponto de entrada do Django para comandos de gerenciamento."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django não encontrado. Ative o virtualenv e instale os requirements."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
