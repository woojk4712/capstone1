"""Read-only publication audit. Never prints credential values or matching lines."""
import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.settings import read_env

SKIP = {'.git', '.venv', 'venv', 'node_modules', '.npm-cache', '__pycache__', '.runtime'}
SIGNATURES = [
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]
ASSIGNMENT = re.compile(
    rb'''(?i)["']?(?:ME_SERVICE_KEY|KEPCO_SERVICE_KEY|service_?key|api_?key|access_?token|auth_?token|password|secret)["']?\s*[:=]\s*["']([^"'\r\n]{24,})["']''')
QUERY_SECRET = re.compile(rb'(?i)(?:[?&]|\b)(?:service_?key|api_?key|access_?token)=([A-Za-z0-9%+/_=.-]{24,})')


def git(args, git_dir=None):
    command = ['git']
    if git_dir:
        command += ['--git-dir=' + str(git_dir), '--work-tree=' + str(ROOT)]
    return subprocess.check_output(command + args, cwd=ROOT, stderr=subprocess.PIPE)


def credentials():
    result = set()
    for name, value in read_env().items():
        if re.search(r'KEY|TOKEN|PASSWORD|SECRET', name, re.I) and len(value) >= 8:
            if value in ('local-development-only', 'changeme', 'your-key-here'):
                continue
            for variant in (value, unquote(value), quote(value, safe='')):
                if len(variant) >= 8:
                    result.add(variant.encode())
    return result


def suspicious(data, known):
    if any(secret in data for secret in known) or any(p.search(data) for p in SIGNATURES):
        return True
    for match in list(ASSIGNMENT.finditer(data)) + list(QUERY_SECRET.finditer(data)):
        value = match.group(1)
        # High-diversity, literal tokens only; ordinary prose and placeholders
        # are not treated as credentials solely because a variable is named KEY.
        if re.fullmatch(rb'[A-Za-z0-9_+/%=.-]+', value) and len(set(value)) >= 16:
            return True
    return False


def forbidden(name):
    p = Path(name)
    return ((p.name == '.env' or p.name.startswith('.env.')) and p.name != '.env.example') or (
        p.suffix.lower() in ('.sqlite', '.sqlite3', '.db', '.log', '.xlsx', '.xls')) or (
        any(part in ('node_modules', '.venv', 'runtime', 'logs', 'raw') for part in p.parts)) or (
        p.suffix.lower() == '.csv' and ('data/input' in p.as_posix() or p.parent == Path('.')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', choices=('workspace', 'candidates', 'staged'), default='candidates')
    parser.add_argument('--git-dir', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    known = credentials()
    if args.scope == 'workspace':
        names = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP and not d.endswith('.git')]
            names += [str((Path(base) / f).relative_to(ROOT)) for f in files]
    else:
        command = ['diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'] if args.scope == 'staged' else [
            'ls-files', '--cached', '--others', '--exclude-standard', '-z']
        names = sorted(set(git(command, args.git_dir).decode().strip('\0').split('\0')) - {''})
    leaks, excluded, unreadable = [], [], []
    for name in names:
        path = ROOT / name
        if path == ROOT / '.env':
            continue
        if args.scope != 'workspace' and forbidden(name):
            excluded.append(name)
        try:
            data = git(['show', ':' + name], args.git_dir) if args.scope == 'staged' else path.read_bytes()
            hit = suspicious(data, known)
            if args.scope == 'workspace' and zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    hit = hit or any(suspicious(archive.read(member), known) for member in archive.infolist()
                                     if not member.is_dir() and member.file_size < 50_000_000)
            elif path.suffix == '.gz':
                hit = hit or suspicious(gzip.decompress(data), known)
            if hit:
                leaks.append(name)
        except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError):
            unreadable.append(name)
    result = {'scope': args.scope, 'files_scanned': len(names), 'secret_scan': 'FAIL' if leaks or unreadable else 'PASS',
              'secret_paths': leaks, 'unreadable_paths': unreadable, 'forbidden_upload_paths': excluded}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('secret scan: ' + result['secret_scan'])
    for name in sorted(set(leaks + unreadable + excluded)):
        print('REVIEW FILE: ' + name)
    print('files scanned: ' + str(len(names)))
    return bool(leaks or unreadable or excluded)


if __name__ == '__main__':
    raise SystemExit(main())
