import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


setup = module('public_setup', 'tools/setup.py')
native = module('public_adapter', 'native/server.py')


class PublicInstallTests(unittest.TestCase):
    def arguments(self, directory):
        root = Path(directory)
        data = root / 'data'
        data.mkdir()
        (data / 'state-SyntheticUser1.json').write_text('{"routines":[]}')
        profiles = root / 'profiles.json'
        profiles.write_text(json.dumps([{'slug': 'user1', 'uid': 'SyntheticUser1', 'name': 'Synthetic'}]))
        return setup.parser().parse_args([
            '--profiles', str(profiles), '--data-dir', str(data),
            '--api-url', 'http://host.docker.internal:8888',
            '--panel-url', 'http://192.0.2.10:8893', '--bind-address', '192.0.2.10',
            '--uid', str(os.getuid() or 1000), '--gid', str(os.getgid() or 1000),
            '--output', str(root / 'private-install'),
        ])

    def test_new_keys_match_services_and_firmware_without_exposing_other_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.arguments(directory)
            source = Path(args.data_dir) / 'state-SyntheticUser1.json'
            before = source.read_bytes()
            out = setup.prepare(args)
            session = json.loads((out / 'sessions.json').read_text())
            adapter = json.loads((out / 'native.json').read_text())
            compose = json.loads((out / 'compose.yaml').read_text())
            self.assertEqual(session['readToken'], adapter['upstreamToken'])
            self.assertEqual(session['writeToken'], adapter['writeToken'])
            self.assertEqual(len({session['readToken'], session['writeToken'], adapter['token']}), 3)
            self.assertEqual(adapter['mediaMode'], 'placeholder')
            self.assertNotIn('ports', compose['services']['sessions'])
            self.assertEqual(compose['services']['native']['ports'], ['192.0.2.10:8893:8893'])
            self.assertTrue(compose['services']['sessions']['volumes'][0]['read_only'])
            self.assertEqual(compose['services']['sessions']['user'], f'{args.uid}:{args.gid}')
            self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir() if p.is_file()))
            self.assertEqual(source.read_bytes(), before)
            self.assertNotIn('admin', session['profiles'][0]['slug'])
            with self.assertRaises(FileExistsError):
                setup.prepare(args)
            self.assertEqual(source.read_bytes(), before)

    def test_default_english_and_explicit_norwegian_match_firmware_and_companion(self):
        for selected, expected in [(None, 'en'), ('nb', 'nb')]:
            with self.subTest(language=selected), tempfile.TemporaryDirectory() as directory:
                args = self.arguments(directory)
                self.assertEqual(args.language, 'en')
                if selected:
                    args.language = selected
                out = setup.prepare(args)
                compose = json.loads((out / 'compose.yaml').read_text())
                installation = json.loads((out / 'installation.json').read_text())
                self.assertEqual(compose['services']['sessions']['environment']['PANEL_LANGUAGE'], expected)
                self.assertEqual(installation['locale']['language'], expected)
                self.assertEqual(installation['locale']['timezone'], args.timezone)
                config = module('installation_locale', 'tools/configure_installation.py')
                wrapper, env = config.render(config.validate(installation))
                self.assertIn('panel_language: "' + expected + '"', wrapper)
                self.assertIn('PANEL_LANGUAGE="' + expected + '"', env)

    def test_duplicate_profiles_and_missing_state_fail_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.arguments(directory)
            values = json.loads(Path(args.profiles).read_text())
            Path(args.profiles).write_text(json.dumps(values * 2))
            with self.assertRaises(ValueError):
                setup.prepare(args)
            self.assertFalse(Path(args.output).exists())
            Path(args.profiles).write_text(json.dumps(values))
            (Path(args.data_dir) / 'state-SyntheticUser1.json').unlink()
            with self.assertRaises(ValueError):
                setup.prepare(args)
            self.assertFalse(Path(args.output).exists())

    def test_urls_and_binding_reject_credentials_and_public_wildcard(self):
        for value in ['file:///data', 'http://user:pass@host', 'http://host/api', 'http://host\nX=1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                setup.origin(value)
        with tempfile.TemporaryDirectory() as directory:
            args = self.arguments(directory)
            args.bind_address = '0.0.0.0'
            with self.assertRaises(ValueError):
                setup.prepare(args)
            self.assertFalse(Path(args.output).exists())

    def test_placeholder_never_opens_or_extracts_exercise_media(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = native.Adapter({'token': 'r' * 32, 'upstreamToken': 'u' * 32}, directory)
            with patch.object(native, 'read_regular', side_effect=AssertionError('Must not read media')), \
                    patch.object(native, 'convert_video', side_effect=AssertionError('Must not decode video')):
                for kind, name in [('still', 'v140-1202.jpg'), ('animation', 'v140-1202.gif')]:
                    payload = adapter.media(kind, name, packed=True)
                    raw = zlib.decompress(payload[8:]) if payload[:4] == b'GYZ1' else payload
                    self.assertEqual(struct.unpack('<4sHHHH', raw[:12]), (b'GYM1', 512, 360, 1, 0))
                    self.assertEqual(len(raw), 12 + 512 * 360 * 2)
                    self.assertIs(payload, adapter.media(kind, name, packed=True))
                    hq = adapter.media(kind, name, packed=True, high_quality=True)
                    raw_hq = zlib.decompress(hq[8:]) if hq[:4] == b'GYZ1' else hq
                    self.assertEqual(struct.unpack('<4sHHHH', raw_hq[:12]),
                                     (b'GYM1', 512, 360, 1, 100 if kind == 'animation' else 0))

            with self.assertRaises(FileNotFoundError):
                adapter.media('still', '../private.jpg')


if __name__ == '__main__':
    unittest.main()
