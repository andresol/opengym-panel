import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('installation', ROOT / 'tools/configure_installation.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads((ROOT / 'config/installation.example.json').read_text())
        self.compat = json.loads((ROOT / 'config/installation.compatibility.json').read_text())

    def test_installed_compatibility_keeps_all_defaults_and_existing_service_credentials(self):
        c = m.validate(self.compat)
        self.assertEqual(c['substitutions'], m.DEFAULTS)
        self.assertEqual(c['network_mode'], 'static')
        text, env = m.render(c)
        self.assertIn('manual_ip:', text)
        self.assertNotIn('gym_native:', text)
        self.assertNotIn('UPSTREAM=', env)
        self.assertNotIn('PANEL_API_ORIGIN=', env)
        self.assertIn('PANEL_TIMEZONE="Europe/Oslo"', env)

    def test_generic_dhcp_other_identity_and_timezone_are_local_overrides(self):
        self.example['locale']['timezone'] = 'America/New_York'
        c = m.validate(self.example)
        text, env = m.render(c)
        self.assertNotIn('manual_ip:', text)
        self.assertIn('panel_name: "gym-panel"', text)
        self.assertIn('panel_timezone: "America/New_York"', text)
        self.assertIn('PANEL_TIMEZONE="America/New_York"', env)
        self.assertIn('PANEL_API_ORIGIN="http://opengym:8888"', env)
        self.assertIn('UPSTREAM="http://sessions:8894"', env)
        self.assertNotIn('token', text)

    def test_english_language_is_explicit_and_matches_firmware_and_backend(self):
        self.example['locale']['language'] = 'en'
        config = m.validate(self.example)
        text, env = m.render(config)
        self.assertIn('panel_language: "en"', text)
        self.assertIn('PANEL_LANGUAGE="en"', env)
        self.assertEqual(config['substitutions']['panel_timezone'], m.DEFAULTS['panel_timezone'])

    def test_invalid_configuration_rejected_before_output(self):
        mutations = [lambda c:c.update(schema=True), lambda c:c.update(secret='x'),
                     lambda c:c['device'].update(name='bad name'),
                     lambda c:c['device'].update(friendly_name='bad\ntext'),
                     lambda c:c['locale'].update(timezone='Invalid/Timezone'),
                     lambda c:c['locale'].update(language='fr'),
                     lambda c:c['network'].update(mode='auto'),
                     lambda c:c['network'].update(address='10.0.0.5'),
                     lambda c:c['services'].update(panel_url='http://user:pass@host'),
                     lambda c:c['services'].update(panel_url='http://host/api'),
                     lambda c:c['services'].update(panel_url='http://host?'),
                     lambda c:c['services'].update(panel_url='http://host#'),
                     lambda c:c['services'].update(panel_url='http://host\nX=1'),
                     lambda c:c['services'].update(panel_url='file:///data'),
                     lambda c:c['services'].update(panel_url='http://bad$(id)'),
                     lambda c:c['services'].update(panel_url='http://bad`id`'),
                     lambda c:c['services'].update(panel_url='http://bad${HOME}'),
                     lambda c:c['services'].update(panel_url='http://host:99999')]
        for mutate in mutations:
            c = copy.deepcopy(self.example)
            mutate(c)
            with self.subTest(config=c), self.assertRaises(ValueError):m.validate(c)

    def test_static_network_validation(self):
        for key, value in [('address','192.0.2.0'),('address','192.0.2.255'),('address',True),
                           ('gateway','198.51.100.1'),('gateway','192.0.2.12'),
                           ('subnet','255.0.255.0'),('dns','0.0.0.0')]:
            c = copy.deepcopy(self.compat);c['network'][key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):m.validate(c)
        c = copy.deepcopy(self.compat)
        c['network'].update(address='10.42.0.30',gateway='10.42.0.1',dns='10.42.0.1')
        self.assertEqual(m.validate(c)['substitutions']['panel_static_ip'],'10.42.0.30')

    def test_files_are_private_and_never_overwrite_existing_configuration(self):
        c=m.validate(self.example)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);secret=p/'secrets.yaml';secret.write_text('existing-secret: unchanged\n')
            paths=m.write(c, firmware_dir=p)
            saved={f:f.read_bytes() for f in paths}
            self.assertTrue(all(stat.S_IMODE(f.stat().st_mode)==0o600 for f in paths))
            with self.assertRaises(FileExistsError):m.write(c, firmware_dir=p)
            self.assertTrue(all(f.read_bytes()==v for f,v in saved.items()))
            self.assertEqual(secret.read_text(),'existing-secret: unchanged\n')
            self.assertNotIn(secret, paths)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):m.load(p)


if __name__ == '__main__':unittest.main()
