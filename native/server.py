#!/usr/bin/env python3
"""Read-only native display adapter. No OpenGym writes, IDs or raw state access.

Plans come from the existing profile-isolated projection on this same host.
Only pinned public catalogue media is converted to bounded RGB565 frames.
"""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import hmac
import json
import math
import os
import re
import struct
import subprocess
import threading
import zlib
import urllib.error
import urllib.request

from PIL import Image, ImageOps, ImageChops, ImageDraw

VERSION = "1.2.1"
ROOT = Path(__file__).resolve().parent
Image.MAX_IMAGE_PIXELS = 8_000_000
MEDIA_LIMIT = 6 * 1024 * 1024
CACHE_LIMIT = 16 * 1024 * 1024


def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        import stat
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Invalid media")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(limit + 1)
    finally:
        os.close(fd)


def rgb565(image, width, height):
    canvas = Image.new("RGB", (width, height), "white")
    sample = ImageOps.contain(image.convert("RGB"), (width - 16, height - 16))
    canvas.paste(sample, ((width - sample.width) // 2, (height - sample.height) // 2))
    # Pillow performs these exact bit operations in C, rather than looping over
    # every pixel in Python. The disjoint channel bits add without saturation.
    red, green, blue = canvas.split()
    low = ImageChops.add(green.point(lambda n: (n >> 2 & 7) << 5),
                         blue.point(lambda n: n >> 3))
    high = ImageChops.add(red.point(lambda n: n & 0xF8),
                          green.point(lambda n: n >> 5))
    # LA is used only as an interleaved two-byte container: low byte, high byte.
    return Image.merge("LA", (low, high)).tobytes()


def convert_media(data, animated=False):
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("Oversized image")
        if not animated:
            return struct.pack("<4sHHHH", b"GYM1", 512, 360, 1, 0) + rgb565(image, 512, 360)

        count = getattr(image, "n_frames", 1)
        if count > 250:
            raise ValueError("Animation too long")
        durations = []
        for i in range(count):
            image.seek(i)
            durations.append(max(20, min(2000, int(image.info.get("duration", 100)))))
        total = sum(durations)
        frames = min(24, max(1, (total + 99) // 100))
        delay = max(100, min(20000, (total + frames - 1) // frames))
        result = bytearray(struct.pack("<4sHHHH", b"GYM1", 320, 224, frames, delay))
        source_index = 0
        end = durations[0]
        for i in range(frames):
            position = min(total - 1, i * delay)
            while source_index + 1 < count and position >= end:
                source_index += 1
                end += durations[source_index]
            image.seek(source_index)
            result.extend(rgb565(image, 320, 224))
        return bytes(result)


def pack_media(raw):
    """GYZ1 declares the bounded GYM1 size; zlib carries its own Adler checksum.

    Keep the legacy raw route compatible with installed RC4 and avoid expanding
    incompressible content on the packed route.
    """
    compressed = b"GYZ1" + struct.pack("<I", len(raw)) + zlib.compress(raw, 6)
    return compressed if len(compressed) < len(raw) else raw


def convert_video(path):
    """Decode one allowlisted local MP4 into the existing bounded GYM1 format.

    One open regular-file descriptor prevents symlink/replacement races. No
    URL, network protocol, arbitrary filter or command is supplied by clients.
    Decoder/filter threads, input bytes, dimensions, duration and output frames
    are bounded independently of the source media.
    """
    import stat
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MEDIA_LIMIT:
            raise ValueError('Invalid video')
        source = f'/proc/self/fd/{descriptor}'
        options = ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-threads', '1']
        probe = subprocess.run(
            ['ffprobe', *options, '-select_streams', 'v:0', '-show_entries',
             'stream=width,height:format=duration', '-of', 'json', source],
            capture_output=True, check=True, timeout=8, pass_fds=(descriptor,),
        )
        metadata = json.loads(probe.stdout)
        stream = metadata['streams'][0]
        duration = float(metadata['format']['duration'])
        if (not math.isfinite(duration) or not 0 < duration <= 120 or
                not 0 < int(stream['width']) * int(stream['height']) <= Image.MAX_IMAGE_PIXELS):
            raise ValueError('Video exceeds bounds')
        frames = min(24, max(1, math.ceil(duration * 10)))
        delay = max(100, math.ceil(duration * 1000 / frames))
        # Start at t=0, retaining the whole movement at a bounded frame rate.
        fps = 1000 / delay
        os.lseek(descriptor, 0, os.SEEK_SET)
        result = subprocess.run(
            ['ffmpeg', '-nostdin', *options, '-i', source, '-an', '-sn', '-dn',
             '-filter_threads', '1', '-vf',
             f'fps=fps={fps:.9f}:start_time=0,'
             'scale=304:208:force_original_aspect_ratio=decrease:force_divisible_by=2,'
             'pad=320:224:(ow-iw)/2:(oh-ih)/2:color=white',
             '-frames:v', str(frames), '-threads:v', '1',
             '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'],
            capture_output=True, check=True, timeout=20, pass_fds=(descriptor,),
        )
        return video_frames(result.stdout, frames, delay)
    finally:
        os.close(descriptor)


def video_frames(data, maximum_frames, delay):
    frame_bytes = 320 * 224 * 3
    count, remainder = divmod(len(data), frame_bytes)
    if remainder or not 1 <= count <= maximum_frames <= 24:
        raise ValueError('Invalid decoded video frames')
    result = bytearray(struct.pack('<4sHHHH', b'GYM1', 320, 224, count, delay))
    for offset in range(0, len(data), frame_bytes):
        frame = Image.frombytes('RGB', (320, 224), data[offset:offset + frame_bytes])
        # No second resize or margins: the decoder already produced the canvas.
        red, green, blue = frame.split()
        low = ImageChops.add(green.point(lambda n: (n >> 2 & 7) << 5), blue.point(lambda n: n >> 3))
        high = ImageChops.add(red.point(lambda n: n & 0xF8), green.point(lambda n: n >> 5))
        result.extend(Image.merge('LA', (low, high)).tobytes())
    return bytes(result)


class Adapter:
    def __init__(self, config, media_dir, upstream="http://sessions:8894", catalogue_media_dir=None):
        self.token = config["token"]
        self.upstream_token = config["upstreamToken"]
        self.write_token = config.get("writeToken")
        if min(len(self.token), len(self.upstream_token)) < 32:
            raise ValueError("Invalid private configuration")
        if self.write_token is not None and (not isinstance(self.write_token, str) or len(self.write_token) < 32 or self.write_token in [self.token, self.upstream_token]):
            raise ValueError("Separate write credential required")
        self.upstream = upstream
        self.media_mode = config.get("mediaMode", "placeholder")
        if self.media_mode not in {"placeholder", "owned"}:
            raise ValueError("Invalid media mode")
        self.media_dir = Path(media_dir)
        self.allowed = set(json.loads((ROOT / "catalogue-media.json").read_text()))
        self.modern = json.loads((ROOT / 'catalogue-modern.json').read_text())['files']
        self.catalogue_media_dir = Path(catalogue_media_dir or os.environ.get('CATALOGUE_MEDIA_DIR', '/catalogue-media'))
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.media_lock = threading.Lock()

    def plan(self, route):
        request = urllib.request.Request(
            self.upstream + route,
            headers={"Authorization": "Bearer " + self.upstream_token},
        )
        # Do not forward a redirect or credentials to a different origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
            data = response.read(64001)
            if len(data) > 64000:
                raise ValueError("Oversized plan")
            json.loads(data)
            return data

    def action(self, route, body):
        request = urllib.request.Request(
            self.upstream + route, data=body, method="POST",
            headers={"Authorization": "Bearer " + self.write_token,
                     "Content-Type": "application/json"},
        )
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=35)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read(64001)
            if len(data) > 64000:
                raise ValueError("Oversized response")
            json.loads(data)
            return response.code, data

    def media(self, kind, filename, packed=False):
        source = ("gif/" if kind == "animation" else "img/") + filename
        if source not in self.allowed and source not in self.modern:
            raise FileNotFoundError("Not catalogue media")
        key = (kind, filename, packed)
        # Serialize conversions and cache ownership, bounding transient RAM/CPU.
        with self.media_lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            if self.media_mode == "placeholder":
                # Original geometric artwork, not derived from exercise media.
                image = Image.new("RGB", (512, 360), "#17191b")
                draw = ImageDraw.Draw(image)
                for x in (164, 188, 300, 324):
                    draw.rounded_rectangle((x, 110, x + 24, 232), 6, fill="#b8ee56")
                draw.rectangle((200, 166, 312, 178), fill="#b8ee56")
                draw.text((256, 274), "No exercise illustration", anchor="mm", fill="white")
                payload = struct.pack("<4sHHHH", b"GYM1", 512, 360, 1, 0) + rgb565(image, 512, 360)
            elif source in self.modern:
                relative = self.modern[source]
                if not re.fullmatch(r'(?:still/[0-9]+\.webp|clip/[0-9]+\.mp4)', relative):
                    raise ValueError('Invalid pinned media source')
                path = self.catalogue_media_dir / relative
                payload = (convert_video(path) if kind == 'animation' else
                           convert_media(read_regular(path, MEDIA_LIMIT)))
            else:
                payload = convert_media(read_regular(self.media_dir / source, MEDIA_LIMIT), kind == "animation")
            if packed:
                payload = pack_media(payload)
            while self.cache and self.cache_bytes + len(payload) > CACHE_LIMIT:
                _, old = self.cache.popitem(last=False)
                self.cache_bytes -= len(old)
            self.cache[key] = payload
            self.cache_bytes += len(payload)
            return payload


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, adapter):
        self.adapter = adapter
        self.slots = threading.BoundedSemaphore(6)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log private profile routes or bearer headers.

    def reply(self, code, data, content_type="application/json"):
        # Large raw catalogue animations need more than the short request-header
        # timeout on an embedded receiver. Keep writes bounded, but do not cut
        # off a healthy transfer after ten seconds.
        self.connection.settimeout(30 if len(data) > 64000 else 10)
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, json.dumps({"ok": True, "version": VERSION, "opengymVersion": "1.4.4", "readOnly": True}).encode())
        auth = self.headers.get("Authorization", "").encode()
        expected = ("Bearer " + self.server.adapter.token).encode()
        if not hmac.compare_digest(auth, expected):
            return self.reply(401, b'{"error":"Unauthorized"}')
        if self.path == "/api/profiles" or re.fullmatch(
            r"/api/profiles/[a-z][a-z0-9-]{0,30}/plan(?:\?(?:day=[0-6](?:&routine=[a-f0-9]{24})?|routine=[a-f0-9]{24}))?", self.path
        ):
            try:
                return self.reply(200, self.server.adapter.plan(self.path))
            except urllib.error.HTTPError as error:
                return self.reply(error.code if error.code in (400, 401, 404, 409) else 503, b'{"error":"Plan unavailable"}')
            except Exception:
                return self.reply(503, b'{"error":"Plan unavailable"}')
        media = re.fullmatch(r"/(native|packed)/(still|animation)/([A-Za-z0-9_-]+\.(?:jpg|png|gif))", self.path)
        if media:
            try:
                return self.reply(200, self.server.adapter.media(media[2], media[3], packed=media[1] == "packed"), "application/vnd.sollie.gym-rgb565")
            except Exception:
                return self.reply(404, b'{"error":"Media unavailable"}')
        self.reply(404, b'{"error":"Not found"}')

    def do_POST(self):
        if self.command != "POST":
            return self.reply(405, b'{"error":"Method not allowed"}')
        token = self.server.adapter.write_token
        if not token or not hmac.compare_digest(
            self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()
        ):
            return self.reply(401, b'{"error":"Unauthorized"}')
        if not re.fullmatch(r"/api/profiles/[a-z][a-z0-9-]{0,30}/action", self.path):
            return self.reply(404, b'{"error":"Not found"}')
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 2 or size > 2048 or self.headers.get_content_type() != "application/json":
                return self.reply(400, b'{"error":"invalid_action"}')
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("Incomplete command")
            json.loads(body)
            code, data = self.server.adapter.action(self.path, body)
            return self.reply(code, data)
        except Exception:
            return self.reply(503, b'{"error":"service_unavailable"}')

    do_PUT = do_PATCH = do_DELETE = do_POST


if __name__ == "__main__":
    config = json.loads(Path(os.environ["PANEL_CONFIG"]).read_text())
    adapter = Adapter(config, os.environ["MEDIA_DIR"], os.environ.get("UPSTREAM", "http://sessions:8894"))
    Server(("0.0.0.0", int(os.environ.get("PORT", "8893"))), adapter).serve_forever()
