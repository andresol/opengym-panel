#!/usr/bin/env python3
"""Render native LVGL documentation fixtures offline; never connects to a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "firmware/custom_components/gym_native"


def fonts():
    import freetype
    chunks = ["struct Glyph {uint32_t cp; int advance,ox,oy,w,h; const unsigned char *bitmap;};",
              "struct FontData {const Glyph *glyphs; unsigned count;};"]
    initializers = []
    alphabet = list(range(32, 127)) + list(map(ord, "ÅÆØåæø↓✓‹›−…×·—→"))
    for size in [16, 18, 20, 30, 42]:
        face = freetype.Face(str(ROOT / "firmware/fonts/DejaVuSans.ttf"))
        face.set_pixel_sizes(size, 0)
        px = lambda value: int((value + 32) // 64)
        height, ascender = px(face.size.height), px(face.size.ascender)
        rows = []
        for cp in alphabet:
            assert face.get_char_index(cp), "Missing screenshot glyph"
            face.load_char(chr(cp), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_BITMAP)
            glyph, bitmap = face.glyph, face.glyph.bitmap
            name = f"glyph_{size}_{cp}"
            data = [(value // 16) * 17 for value in bitmap.buffer]
            chunks.append("static const unsigned char " + name + "[]={" +
                          ",".join(map(str, data or [0])) + "};")
            rows.append("{" + ",".join(map(str, [cp, px(glyph.metrics.horiAdvance),
                        glyph.bitmap_left, glyph.bitmap_top - bitmap.rows,
                        bitmap.width, bitmap.rows])) + "," + name + "}")
        chunks.append(f"static const Glyph glyphs{size}[]={{" + ",".join(rows) + "};")
        chunks.append(f"static FontData data{size}{{glyphs{size},{len(rows)}}};")
        chunks.append(f"static lv_font_t f{size};")
        initializers.append(f"f{size}.get_glyph_dsc=glyph_dsc; f{size}.get_glyph_bitmap=glyph_bitmap; "
                            f"f{size}.line_height={height}; f{size}.base_line={height-ascender}; "
                            f"f{size}.static_bitmap=1; f{size}.dsc=&data{size};")
    chunks.append(r"""
static bool glyph_dsc(const lv_font_t *font, lv_font_glyph_dsc_t *out, uint32_t cp, uint32_t) {
  const auto &data = *static_cast<const FontData *>(font->dsc);
  for (unsigned i = 0; i < data.count; ++i) {
    const auto &g = data.glyphs[i];
    if (g.cp != cp) continue;
    out->adv_w=g.advance; out->ofs_x=g.ox; out->ofs_y=g.oy;
    out->box_w=g.w; out->box_h=g.h; out->format=LV_FONT_GLYPH_FORMAT_A8;
    out->is_placeholder=0; out->gid.index=i; return true;
  }
  return false;
}
static const void *glyph_bitmap(lv_font_glyph_dsc_t *out, lv_draw_buf_t *) {
  const auto &data = *static_cast<const FontData *>(out->resolved_font->dsc);
  return data.glyphs[out->gid.index].bitmap;
}
""")
    return "\n".join(chunks), "\n".join(initializers)


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["lvgl-include", "lvgl-library", "lvgl-config"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    cpp = (COMPONENT / "gym_native.cpp").read_text()
    ui = (COMPONENT / "workout_ui.cpp").read_text()
    header = (COMPONENT / "gym_native.h").read_text()
    methods = between(cpp, "lv_obj_t *GymNative::box(", "void GymNative::click(")
    methods += between(cpp, "void GymNative::begin(", "bool GymNative::accept_people(")
    methods += between(cpp, "void GymNative::render_timer(", "void GymNative::loop(")
    methods += between(ui, "void GymNative::render_session(", "void GymNative::session_action(")
    people = between(cpp, "  for (size_t i = 0; i < people_.size(); ++i) {", '  update_status("");')
    structures = between(header, "struct Person {", "class GymNative :")
    from PIL import Image, ImageOps
    illustration_path = ROOT / "docs/images/barbell-squat-original.png"
    original = Image.open(illustration_path).convert("RGBA")
    fitted = ImageOps.contain(original, (512, 360), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (512, 360), "#17191b")
    canvas.alpha_composite(fitted, ((512 - fitted.width) // 2, (360 - fitted.height) // 2))
    # This is the native viewport's rendering input, not an edited source asset.
    pixels = canvas.convert("RGB").tobytes("raw", "BGR")
    illustration = "static const unsigned char readme_pixels[]={" + ",".join(map(str, pixels)) + "};"
    illustration += r"""
static lv_image_dsc_t readme_illustration;
static void prepare_illustration() {
  readme_illustration.header.magic = LV_IMAGE_HEADER_MAGIC;
  readme_illustration.header.cf = LV_COLOR_FORMAT_RGB888;
  readme_illustration.header.w = 512;
  readme_illustration.header.h = 360;
  readme_illustration.header.stride = 512 * 3;
  readme_illustration.data_size = sizeof(readme_pixels);
  readme_illustration.data = readme_pixels;
}
"""
    font_data, font_init = fonts()
    source = (ROOT / "tools/readme_fixture.cpp").read_text()
    for marker, value in [("FONT_DATA", font_data), ("FONT_INIT", font_init),
                          ("STRUCTURES", structures), ("METHODS", methods), ("PEOPLE", people),
                          ("EXERCISE_IMAGE_DATA", illustration)]:
        source = source.replace("/* " + marker + " */", value)
    output = ROOT / "docs/images"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opengym-readme-") as folder:
        temporary = Path(folder)
        (temporary / "render.cpp").write_text(source)
        subprocess.run(["g++", "-std=c++17", "-I" + str(args.lvgl_include.resolve()),
                        "-I" + str(COMPONENT), '-DLV_CONF_PATH="' + str(args.lvgl_config.resolve()) + '"',
                        str(temporary / "render.cpp"), str(args.lvgl_library.resolve()),
                        "-lm", "-o", str(temporary / "render")], check=True)
        result = subprocess.check_output([str(temporary / "render")], cwd=temporary, text=True)
        images = {}
        for line in result.splitlines():
            if not line.startswith("snapshot "):
                continue
            _, name, width, height, stride = line.split()
            image = Image.frombytes("RGB", (int(width), int(height)),
                                    (temporary / name).read_bytes(), "raw", "BGR", int(stride), 1)
            path = output / (Path(name).stem + ".png")
            image.save(path, optimize=True)
            images[path.relative_to(ROOT).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "width": image.width, "height": image.height,
                "kind": "synthetic-native-lvgl-desktop-render",
            }
        assert set(images) == {"docs/images/profiles.png", "docs/images/workout.png"}
        images[illustration_path.relative_to(ROOT).as_posix()] = {
            "sha256": hashlib.sha256(illustration_path.read_bytes()).hexdigest(),
            "width": original.width, "height": original.height,
            "kind": "original-ai-exercise-illustration",
        }
        provenance = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in [COMPONENT / "gym_native.cpp", COMPONENT / "gym_native.h",
                                   COMPONENT / "workout_ui.cpp", ROOT / "tools/readme_fixture.cpp",
                                   ROOT / "tools/render_readme.py", illustration_path]}
        (output / "manifest.json").write_text(json.dumps({"schema": 1, "images": images,
            "source_hashes": provenance, "real_user_data": False, "hardware_capture": False,
            "network_access": False, "restricted_exercise_media": False}, indent=2) + "\n")
        print("Rendered two offline synthetic native-LVGL images; review before publishing.")


if __name__ == "__main__":
    main()
