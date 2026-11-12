#!/usr/bin/env python3
"""Validate non-secret installation settings and generate local overrides. Never deploys."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = json.loads((ROOT / 'firmware/config/installation.defaults.json').read_text())['substitutions']


def object_keys(value, allowed, context):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('Invalid or unknown fields in ' + context)
    return value


def string(value, limit=160):
    if not isinstance(value, str) or not value or len(value) > limit or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Invalid text value')
    return value


def url(value):
    string(value, 256)
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError as e:
        raise ValueError('Invalid service origin') from e
    if u.scheme not in ('http', 'https') or not u.hostname or u.username is not None or u.password is not None or u.path not in ('', '/') or '?' in value or '#' in value or any(c.isspace() for c in value) or (port is not None and port == 0):
        raise ValueError('Service origin must be HTTP(S), without credentials, path, query or fragment')
    host = u.hostname.rstrip('.')
    if ':' in host:
        try: ipaddress.IPv6Address(host)
        except ValueError as e: raise ValueError('Invalid service hostname') from e
    elif len(host) > 253 or not all(re.fullmatch(r'[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?', part) for part in host.split('.')):
        raise ValueError('Invalid service hostname')
    return value.rstrip('/')


def validate(config):
    object_keys(config, ['schema', 'device', 'locale', 'network', 'services'], 'installation')
    if type(config.get('schema')) is not int or config['schema'] != 1:
        raise ValueError('Unsupported installation schema')
    device = object_keys(config.get('device', {}), ['name', 'friendly_name'], 'device')
    locale = object_keys(config.get('locale', {}), ['timezone', 'language'], 'locale')
    network = object_keys(config.get('network', {}), ['mode', 'address', 'gateway', 'subnet', 'dns'], 'network')
    services = object_keys(config.get('services', {}), ['panel_url', 'session_upstream', 'opengym_api'], 'services')
    values = dict(DEFAULTS)
    values['panel_name'] = string(device.get('name', values['panel_name']), 31)
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', values['panel_name']):
        raise ValueError('Invalid ESPHome device name')
    values['panel_friendly_name'] = string(device.get('friendly_name', values['panel_friendly_name']), 80)
    values['panel_timezone'] = string(locale.get('timezone', values['panel_timezone']), 80)
    try:
        ZoneInfo(values['panel_timezone'])
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError('Invalid IANA timezone') from e
    values['panel_language'] = locale.get('language', values['panel_language'])
    if values['panel_language'] != 'nb':
        raise ValueError('Only the existing nb UI is supported; translation is not part of this step')
    mode = network.get('mode', 'dhcp')
    if mode not in ('dhcp', 'static'):
        raise ValueError('Network mode must be dhcp or static')
    if mode == 'dhcp' and set(network) - {'mode'}:
        raise ValueError('DHCP must not silently ignore static address fields')
    if mode == 'static':
        if set(network) != {'mode', 'address', 'gateway', 'subnet', 'dns'}:
            raise ValueError('Static network requires address, gateway, subnet and DNS')
        for key in ['address', 'gateway', 'subnet', 'dns']:
            string(network[key], 32)
        try:
            address, gateway, dns = [ipaddress.IPv4Address(network[key]) for key in ['address', 'gateway', 'dns']]
            subnet = ipaddress.IPv4Network(str(address) + '/' + network['subnet'], strict=False)
        except (ValueError, TypeError) as e:
            raise ValueError('Invalid IPv4 network') from e
        if any(v.is_multicast or v.is_unspecified or v.is_loopback for v in [address, gateway, dns]) or gateway not in subnet or address == gateway or address in [subnet.network_address, subnet.broadcast_address] or gateway in [subnet.network_address, subnet.broadcast_address]:
            raise ValueError('Invalid host or gateway for static subnet')
        for target, key in [('panel_static_ip', 'address'), ('panel_gateway', 'gateway'), ('panel_subnet', 'subnet'), ('panel_dns', 'dns')]:
            values[target] = str(subnet.netmask) if key == 'subnet' else str(network[key])
    service_values = {key: url(value) for key, value in services.items()}
    return {'schema': 1, 'substitutions': values, 'network_mode': mode, 'services': service_values}


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate configuration field')
        result[key] = value
    return result


def load(path):
    return validate(json.loads(Path(path).read_text(), object_pairs_hook=no_duplicate_keys))


def render(config):
    # JSON-quoted scalar values are valid YAML; text cannot inject new YAML keys.
    lines = ['# Generated local configuration. NOT an instruction to install.',
             '# Build with the same private secrets.yaml; existing keys are never rewritten.',
             'packages:', '  production: !include opengym-v3.yaml', 'substitutions:']
    for key, value in config['substitutions'].items():
        lines.append('  ' + key + ': ' + json.dumps(value, ensure_ascii=False))
    if config['network_mode'] == 'dhcp':
        pass  # The community base uses DHCP already.
    else:
        lines.extend(['wifi:', '  manual_ip:', '    static_ip: ${panel_static_ip}',
                      '    gateway: ${panel_gateway}', '    subnet: ${panel_subnet}', '    dns1: ${panel_dns}'])
    if 'panel_url' in config['services']:
        lines.extend(['gym_native:', '  url: ' + json.dumps(config['services']['panel_url'])])
    env = {'PANEL_TIMEZONE': config['substitutions']['panel_timezone'], 'PANEL_LANGUAGE': config['substitutions']['panel_language']}
    for source, target in [('session_upstream', 'UPSTREAM'), ('opengym_api', 'PANEL_API_ORIGIN')]:
        if source in config['services']:
            env[target] = config['services'][source]
    return '\n'.join(lines) + '\n', '# Non-secret process settings; keep private token/profile config unchanged.\n' + ''.join(key + '=' + json.dumps(value) + '\n' for key, value in env.items())


def write(config, name='installation', firmware_dir=None):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', name):
        raise ValueError('Invalid output name')
    folder = Path(firmware_dir) if firmware_dir else ROOT / 'firmware'
    text, env = render(config)
    outputs = {folder / (name + '.local.yaml'): text, folder / (name + '.local.env'): env,
               folder / (name + '.local.json'): json.dumps(config, ensure_ascii=False, indent=2) + '\n'}
    if any(p.exists() or p.is_symlink() for p in outputs):
        raise FileExistsError('Existing local configuration is never overwritten; choose another --name')
    created = []
    try:
        for path, content in outputs.items():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        for path in created:
            path.unlink()
        raise
    return list(outputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--name', default='installation')
    parser.add_argument('--check', action='store_true', help='Validate without writing files')
    args = parser.parse_args()
    try:
        config = load(args.config)
        if args.check:
            print('Installation settings valid; no files or live settings changed.')
        else:
            for path in write(config, args.name):
                print(path.relative_to(ROOT))
            print('Local overrides only. Nothing built, restarted, paired or installed.')
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, str(error) + '\n')
