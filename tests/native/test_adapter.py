import importlib.util
import json
from io import BytesIO
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zlib
import random
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_adapter', ROOT / 'native/server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeAdapterTests(unittest.TestCase):
    def test_rgb565_layout_and_animation_bound(self):
        image = module.Image.new('RGB', (32, 32), (255, 0, 0))
        data = BytesIO()
        image.save(data, format='PNG')
        output = module.convert_media(data.getvalue())
        self.assertEqual(struct.unpack('<4sHHHH', output[:12]), (b'GYM1', 512, 360, 1, 0))
        self.assertEqual(len(output), 12 + 512 * 360 * 2)
        # Centre is red, little-endian RGB565; the background is white.
        middle = 12 + (180 * 512 + 256) * 2
        self.assertEqual(output[middle:middle + 2], b'\x00\xf8')
        self.assertEqual(output[12:14], b'\xff\xff')
        frames = [module.Image.new('RGB', (24, 24), color) for color in ['red', 'green', 'blue']]
        data = BytesIO()
        frames[0].save(data, format='GIF', save_all=True, append_images=frames[1:], duration=120, loop=0)
        output = module.convert_media(data.getvalue(), True)
        magic, width, height, count, delay = struct.unpack('<4sHHHH', output[:12])
        self.assertEqual((magic, width, height), (b'GYM1', 320, 224))
        self.assertTrue(1 <= count <= 24 and delay >= 100)
        self.assertEqual(len(output), 12 + width * height * count * 2)

    def test_hq_still_and_animation_have_identical_pixels_and_margins(self):
        # This catches the actual old bug: an 8 px small-frame margin became
        # ~13 px after panel enlargement, making the subject visibly shrink.
        for dimensions in [(720, 480), (360, 640), (640, 360), (100, 100)]:
            with self.subTest(dimensions=dimensions):
                image = module.Image.new('RGB', dimensions, 'white')
                image.paste('red', (dimensions[0] // 8, dimensions[1] // 8,
                                    dimensions[0] * 7 // 8, dimensions[1] * 7 // 8))
                encoded = BytesIO()
                image.save(encoded, format='GIF', duration=300)
                still = module.convert_media(encoded.getvalue())
                animation = module.convert_media(encoded.getvalue(), True, high_quality=True)
                magic, width, height, count, delay = struct.unpack('<4sHHHH', animation[:12])
                self.assertEqual((magic, width, height, count, delay), (b'GYM1', 512, 360, 3, 100))
                size = width * height * 2
                for frame in range(count):
                    self.assertEqual(animation[12 + frame * size:12 + (frame + 1) * size], still[12:])

    def test_hq_preserves_movement_sampling_and_transport_memory_bound(self):
        frames = [module.Image.new('RGB', (40, 40), color) for color in ['red', 'blue']]
        encoded = BytesIO()
        frames[0].save(encoded, format='GIF', save_all=True, append_images=frames[1:],
                       duration=1800, loop=0)
        old = module.convert_media(encoded.getvalue(), True)
        hq = module.convert_media(encoded.getvalue(), True, high_quality=True)
        self.assertEqual(struct.unpack('<4sHHHH', hq[:12]), (b'GYM1', 512, 360, 24, 150))
        self.assertEqual(hq[8:12], old[8:12])  # No motion/frame-rate downgrade.
        self.assertEqual(len(hq), 8_847_372)
        self.assertEqual(hq[12:14], b'\xff\xff')
        packed = module.pack_media(hq)
        self.assertLess(len(packed), 2 * 1024 * 1024)
        self.assertEqual(zlib.decompress(packed[8:]), hq)
        # A large weakly compressible wire body must not coexist with another
        # equally large expansion on PSRAM. Raw is validated without a copy.
        noisy = random.Random(43).randbytes(3_600_000)
        self.assertIs(module.pack_media(noisy), noisy)

    def test_fast_rgb565_preserves_all_channel_bits(self):
        randomizer = random.Random(42)
        image = module.Image.new('RGB', (32, 32))
        image.putdata([(randomizer.randrange(256), randomizer.randrange(256),
                        randomizer.randrange(256)) for _ in range(1024)])
        output = module.rgb565(image, 48, 48)
        expected = bytearray()
        pixels = image.tobytes()
        for i in range(0, len(pixels), 3):
            red, green, blue = pixels[i:i + 3]
            value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
            expected.extend(struct.pack('<H', value))
        # 16-pixel total margin leaves the original 32x32 image unscaled.
        centre = b''.join(output[((y + 8) * 48 + 8) * 2:
                                  ((y + 8) * 48 + 40) * 2] for y in range(32))
        self.assertEqual(centre, expected)

    def test_packed_protocol_roundtrip_and_raw_fallback(self):
        raw = b'GYM1' + b'\0' * 50000
        packed = module.pack_media(raw)
        self.assertEqual(packed[:4], b'GYZ1')
        self.assertEqual(struct.unpack('<I', packed[4:8])[0], len(raw))
        self.assertEqual(zlib.decompress(packed[8:]), raw)
        self.assertLess(len(packed), len(raw) // 10)
        raw = random.Random(42).randbytes(4096)
        self.assertEqual(module.pack_media(raw), raw)

    def test_private_routes_allowlist_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = module.Adapter({'mediaMode': 'owned', 'token': 'n' * 32, 'upstreamToken': 'u' * 32}, directory)
            requests = []

            def plan(route):
                requests.append(route)
                if '/missing/' in route:
                    raise urllib.error.HTTPError('test', 404, 'missing', {}, None)
                if '/removed/' in route:
                    raise urllib.error.HTTPError('test', 409, 'removed', {}, None)
                return json.dumps({'profileSlug': 'blair', 'entries': []}).encode()

            adapter.plan = plan
            media_calls = []
            def media(kind, filename, packed=False, high_quality=False):
                media_calls.append((kind, filename, packed, high_quality))
                if filename == 'known.png': return b'GYZ1' + b'fake-payload'
                raise FileNotFoundError()
            adapter.media = media
            server = module.Server(('127.0.0.1', 0), adapter)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(server.server_port)

            def get(route, auth=True, method='GET'):
                request = urllib.request.Request(base + route, method=method,
                    headers={'Authorization': 'Bearer ' + 'n' * 32} if auth else {})
                try:
                    with urllib.request.urlopen(request, timeout=3) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            try:
                self.assertEqual(get('/health', False)[0], 200)
                self.assertEqual(get('/packed/still/known.png', False)[0], 401)
                self.assertEqual(get('/packed/still/known.png')[0], 200)
                self.assertEqual(media_calls[-1], ('still', 'known.png', True, False))
                self.assertEqual(get('/native/still/known.png')[0], 200)
                self.assertEqual(media_calls[-1], ('still', 'known.png', False, False))
                self.assertEqual(get('/packed-hq/animation/known.png', False)[0], 401)
                self.assertEqual(get('/packed-hq/animation/known.png')[0], 200)
                self.assertEqual(media_calls[-1], ('animation', 'known.png', True, True))
                self.assertEqual(get('/api/profiles', False)[0], 401)
                code, response = get('/api/profiles/blair/plan?day=2')
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(response)['profileSlug'], 'blair')
                self.assertEqual(get('/api/profiles/missing/plan')[0], 404)
                self.assertEqual(requests, ['/api/profiles/blair/plan?day=2', '/api/profiles/missing/plan'])
                choice = 'a' * 24
                route = '/api/profiles/blair/plan?day=2&routine=' + choice
                self.assertEqual(get(route)[0], 200)
                self.assertEqual(requests[-1], route)
                self.assertEqual(get('/api/profiles/blair/plan?routine=' + choice)[0], 200)
                self.assertEqual(get('/api/profiles/removed/plan?routine=' + choice)[0], 409)
                for route in ['/api/profiles/alex/plan?uid=other', '/api/profiles/alex/plan?day=7',
                              '/api/profiles/alex/plan?day=2&day=1', '/native/still/../../private.png',
                              '/native/still/private.jpg', '/api/profiles/blair/plan?routine=raw-id',
                              '/api/profiles/blair/plan?routine=' + choice + '&uid=other',
                              '/api/profiles/blair/plan?routine=' + choice + '&routine=' + choice]:
                    self.assertEqual(get(route)[0], 404)
                self.assertEqual(get('/api/profiles/blair/plan', method='POST')[0], 401)
                self.assertEqual(get('/api/profiles/blair/plan', method='DELETE')[0], 405)
            finally:
                server.shutdown()
                server.server_close()

    def test_action_frontend_requires_distinct_write_key_and_preserves_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            read_key, write_key = 'r' * 40, 'w' * 40
            adapter = module.Adapter({'mediaMode': 'owned', 'token': read_key, 'upstreamToken': 'u' * 40, 'writeToken': write_key}, directory)
            calls = []
            def action(route, body):
                calls.append((route, json.loads(body)))
                return 409, b'{"error":"session_changed"}'
            adapter.action = action
            server = module.Server(('127.0.0.1', 0), adapter)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            def send(route, key, payload=None, raw=None):
                req = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + route,
                    method='POST', data=raw if raw is not None else json.dumps(payload or {}).encode(),
                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(req, timeout=3) as r: return r.status, r.read()
                except urllib.error.HTTPError as e: return e.code, e.read()
            try:
                route = '/api/profiles/alpha/action'
                self.assertEqual(send(route, read_key)[0], 401)
                self.assertEqual(send(route + '?uid=other', write_key)[0], 404)
                status, body = send(route, write_key, {'action': 'set'})
                self.assertEqual(status, 409)
                self.assertEqual(json.loads(body)['error'], 'session_changed')
                self.assertEqual(calls, [(route, {'action': 'set'})])
                self.assertEqual(send(route, write_key, raw=b'{' + b'x' * 2048)[0], 400)
            finally:
                server.shutdown(); server.server_close()
            with self.assertRaises(ValueError):
                module.Adapter({'mediaMode': 'owned', 'token': read_key, 'upstreamToken': 'u' * 40, 'writeToken': read_key}, directory)

    def test_media_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target').write_bytes(b'private')
            (root / 'link').symlink_to(root / 'target')
            with self.assertRaises(OSError):
                module.read_regular(root / 'link', 1000)
            with self.assertRaises(ValueError):
                module.read_regular(root / 'target', 2)


if __name__ == '__main__':
    unittest.main()
