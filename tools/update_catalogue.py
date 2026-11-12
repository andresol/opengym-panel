#!/usr/bin/env python3
"""Add current public metadata without altering the pinned legacy exercises.

This updates metadata only. It never reads, copies or downloads exercise media.
Virtual jpg/gif names preserve the installed firmware's media URL contract.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'vendor/opengym/frontend/src/lib'


def dataset(path):
    module = json.dumps(path.resolve().as_uri())
    script = f'import {{ EXDB }} from {module}; process.stdout.write(JSON.stringify(EXDB));'
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script]))


def generate(source, version):
    current = dataset(source)
    new_ids = {row['id'] for row in current}
    if len(new_ids) != len(current):
        raise ValueError('Duplicate exercise IDs')
    files = {}
    for original in current:
        row = dict(original)
        for field, route, directory, suffix in [
            ('img', 'img', 'still', 'jpg'),
            ('gif', 'gif', 'clip', 'gif'),
        ]:
            source_name = row[field]
            if Path(source_name).name != source_name:
                raise ValueError('Invalid catalogue filename')
            alias = f"v140-{row['id']}.{suffix}"
            row[field] = alias
            files[f'{route}/{alias}'] = f'{directory}/{source_name}'
    manifest = {
        'schema': 1, 'source_version': version,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'total_count': len(current), 'files': files,
    }
    (ROOT / 'native/catalogue-modern.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: value for key, value in manifest.items() if key != 'files'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    generate(args.source, args.version)
