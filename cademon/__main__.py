
from __future__ import annotations

import argparse
import os

from . import db
from .config import Config
from .env import load_env_file
from .monitor import check_due_processes, check_process, run_worker
from .scraper import fetch_snapshot
from .web import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m cademon')
    parser.add_argument('--env', default='.env', help='Arquivo de configuracao .env')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('init', help='Cria/atualiza o banco SQLite')

    serve = sub.add_parser('serve', help='Inicia o painel web')
    serve.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    serve.add_argument('--port', type=int, default=int(os.getenv('PORT', '8000')))

    sub.add_parser('worker', help='Inicia o verificador continuo')
    sub.add_parser('check-due', help='Executa uma rodada de checagem dos processos vencidos')

    check = sub.add_parser('check', help='Checa um processo especifico')
    check.add_argument('--id', type=int, required=True)
    check.add_argument('--notify-initial', action='store_true')

    probe = sub.add_parser('probe', help='Testa a extracao de texto de uma URL publica')
    probe.add_argument('--url', required=True)

    sub.add_parser('list', help='Lista os processos cadastrados')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    os.environ['CADEMON_ENV_PATH'] = args.env
    load_env_file(args.env)
    cfg = Config.from_env()

    if not args.command:
        parser.print_help()
        return 2

    if args.command == 'init':
        conn = db.connect(cfg.db_path)
        conn.close()
        print(f'Banco pronto em {cfg.db_path}')
        return 0

    if args.command == 'serve':
        db.connect(cfg.db_path).close()
        run_server(cfg, args.host, args.port)
        return 0

    if args.command == 'worker':
        run_worker(cfg)
        return 0

    if args.command == 'check-due':
        conn = db.connect(cfg.db_path)
        try:
            for result in check_due_processes(conn, cfg):
                print(f"#{result.get('process_id')} {result.get('label')}: {result.get('message')}")
        finally:
            conn.close()
        return 0

    if args.command == 'check':
        conn = db.connect(cfg.db_path)
        try:
            result = check_process(conn, cfg, args.id, notify_initial=args.notify_initial)
            print(result.get('message'))
            return 0 if result.get('ok') else 1
        finally:
            conn.close()

    if args.command == 'probe':
        snapshot = fetch_snapshot(args.url, cfg.request_timeout_seconds, cfg.user_agent)
        print(f'Titulo: {snapshot.title or "-"}')
        print(f'Hash: {snapshot.hash}')
        print(f'Tamanho: {snapshot.content_length} bytes')
        print('Trecho extraido:')
        print(snapshot.text[:2000])
        return 0

    if args.command == 'list':
        conn = db.connect(cfg.db_path)
        try:
            for process in db.list_processes(conn):
                print(f"#{process['id']} {process['label']} - {process['public_url']}")
        finally:
            conn.close()
        return 0

    parser.print_help()
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
