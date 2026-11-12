import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('modern_adapter', ROOT / 'native/server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ModernMediaTests(unittest.TestCase):
    def test_webp_alias_and_cache_preserve_firmware_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'still').mkdir()
            module.Image.new('RGB', (180, 180), 'red').save(root / 'still/1202.webp')
            adapter = module.Adapter({'mediaMode': 'owned', 'token': 'r' * 32, 'upstreamToken': 'u' * 32},
                                     root, catalogue_media_dir=root)
            output = adapter.media('still', 'v140-1202.jpg', packed=True)
            raw = module.zlib.decompress(output[8:]) if output[:4] == b'GYZ1' else output
            self.assertEqual(struct.unpack('<4sHHHH', raw[:12]), (b'GYM1', 512, 360, 1, 0))
            self.assertIs(output, adapter.media('still', 'v140-1202.jpg', packed=True))
            for filename in ['1202.webp', '../1202.webp', 'v140-unknown.jpg', 'v140-1202.gif']:
                with self.assertRaises(FileNotFoundError):
                    adapter.media('still', filename)

    def test_video_decoder_retains_timing_bounds_and_single_local_input(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / '1202.mp4'
            video.write_bytes(b'fixture')
            probe = {'streams': [{'width': 180, 'height': 180}], 'format': {'duration': '3.6'}}
            frames = bytes([255, 0, 0]) * (320 * 224 * 24)
            responses = [subprocess.CompletedProcess([], 0, json.dumps(probe).encode()),
                         subprocess.CompletedProcess([], 0, frames)]
            with patch.object(module.subprocess, 'run', side_effect=responses) as run:
                output = module.convert_video(video)
            self.assertEqual(struct.unpack('<4sHHHH', output[:12]), (b'GYM1', 320, 224, 24, 150))
            self.assertEqual(output[12:14], b'\x00\xf8')
            for call in run.call_args_list:
                self.assertIn('file,pipe', call.args[0])
                self.assertEqual(len(call.kwargs['pass_fds']), 1)
                self.assertLessEqual(call.kwargs['timeout'], 20)
                self.assertNotIn('shell', call.kwargs)

    def test_invalid_duration_output_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / 'video.mp4'
            video.write_bytes(b'fixture')
            for duration in ['nan', '0', '121']:
                probe = {'streams': [{'width': 180, 'height': 180}], 'format': {'duration': duration}}
                with patch.object(module.subprocess, 'run', return_value=
                                  subprocess.CompletedProcess([], 0, json.dumps(probe).encode())):
                    with self.assertRaises(ValueError):
                        module.convert_video(video)
            link = Path(directory) / 'link.mp4'
            link.symlink_to(video)
            with self.assertRaises(OSError):
                module.convert_video(link)
        for data in [b'', b'incomplete', b'x' * (320 * 224 * 3 * 25)]:
            with self.assertRaises(ValueError):
                module.video_frames(data, 24, 100)


if __name__ == '__main__':
    unittest.main()
