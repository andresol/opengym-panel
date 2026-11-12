#!/usr/bin/env python3
"""Protect the audited upstream driver set and non-installable v3 build gate."""
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


class Loader(yaml.SafeLoader):
    pass


Loader.add_multi_constructor('!', lambda loader, tag, node: loader.construct_scalar(node))
hardware = yaml.load((ROOT / 'firmware/hardware/jc8012p4a1-v3.yaml').read_text(), Loader=Loader)
smoke = yaml.load((ROOT / 'firmware/v3-hardware-check.yaml').read_text(), Loader=Loader)
assert hardware['esp32']['engineering_sample'] is False
assert hardware['esp32']['framework']['version'] == '5.5.5'
assert hardware['display'][0]['model'] == 'CUSTOM'
assert len(hardware['display'][0]['init_sequence']) > 200
assert hardware['touchscreen'][0]['transform'] == {
    'swap_xy': False, 'mirror_x': True, 'mirror_y': False,
}
assert smoke['wifi']['ssid'] == 'BUILD_ONLY_DO_NOT_INSTALL'
assert smoke['esphome']['project']['name'] == 'sollie.opengym-v3-hardware-check'

components = ROOT / 'firmware/custom_components_v3'
manifest = json.loads((components / 'upstream.json').read_text())
assert manifest['commit'] == '9bf8567f1272b0b2bbe7788de95e8772620561bf'
for name, digest in manifest['files'].items():
    assert hashlib.sha256((components / name).read_bytes()).hexdigest() == digest, name
actual = {
    str(p.relative_to(components)) for part in ['gsl3680', 'mipi_dsi']
    for p in (components / part).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts
}
assert actual == set(manifest['files'])
driver = (components / 'mipi_dsi/mipi_dsi.cpp').read_text()
assert '.phy_clk_src = {}' in driver
assert 'MIPI_DSI_PHY_CLK_SRC_DEFAULT' not in driver
assert 'verify_firmware()' in (components / 'gsl3680/gsl3680.cpp').read_text()

partitions = (ROOT / 'firmware/hardware/partitions-espcontrol-v3.csv').read_text()
assert '0x20000' in partitions and '0x710000' in partitions and '0x6f0000' in partitions
print(f'V3 production/display/touch/recovery gates: PASS; {len(actual)} pinned upstream files')
