"""Audit every installed package, mapping official CPU torch to its upstream version.

pip-audit's PyPI service cannot look up the official '+cpu' local wheel suffix.
Only that suffix is normalized; the complete installed graph stays in scope.
This checks known package advisories, not wheel provenance or binary contents.
"""

from importlib.metadata import distributions
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    requirements = []
    for distribution in distributions():
        name = distribution.metadata['Name']
        version = distribution.version
        if name.lower().replace('_', '-') == 'torch' and version.endswith('+cpu'):
            version = version.removesuffix('+cpu')
            print(f'Auditing official CPU torch against upstream advisory version {version}', flush=True)
        requirements.append(f'{name}=={version}')
    with tempfile.TemporaryDirectory(prefix='nova-evaluation-audit-') as directory:
        manifest = Path(directory) / 'installed-requirements.txt'
        manifest.write_text('\n'.join(sorted(set(requirements))) + '\n', encoding='utf-8')
        # No dependency resolution is needed: this manifest already lists the
        # entire installed graph. Strict mode fails if any package is unauditable.
        subprocess.run([
            sys.executable, '-m', 'pip_audit', '--strict', '--no-deps',
            '--disable-pip', '-r', str(manifest),
        ], check=True)


if __name__ == '__main__':
    main()
