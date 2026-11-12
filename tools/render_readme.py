#!/usr/bin/env python3
"""Render native LVGL documentation fixtures offline; never connects to a device."""
import argparse
import hashlib
import importlib.util
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
    parser.add_argument("--exercise-image", type=Path,
                        help="Optional lawfully supplied squat still; never downloaded or copied to public source")
    parser.add_argument("--language", choices=['nb', 'en'], default='nb')
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/images")
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
    font_data, font_init = fonts()
    source = (ROOT / "tools/readme_fixture.cpp").read_text()
    for marker, value in [("FONT_DATA", font_data), ("FONT_INIT", font_init),
                          ("STRUCTURES", structures), ("METHODS", methods), ("PEOPLE", people)]:
        source = source.replace("/* " + marker + " */", value)
    source = source.replace("/* ENGLISH */", "true" if args.language == 'en' else "false")
    from PIL import Image
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opengym-readme-") as folder:
        temporary = Path(folder)
        (temporary / "render.cpp").write_text(source)
        command = [str(temporary / "render")]
        artwork = None
        if args.exercise_image:
            spec = importlib.util.spec_from_file_location("native_media", ROOT / "native/server.py")
            adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(adapter)
            original = args.exercise_image.read_bytes()
            frame = temporary / "exercise.gym"
            frame.write_bytes(adapter.convert_media(original))
            command.append(str(frame))
            artwork = {"exercise": "barbell full squat", "catalogue_id": "0043",
                       "source_sha256": hashlib.sha256(original).hexdigest(),
                       "processing": "Unchanged native adapter RGB565 still conversion and LVGL image binding",
                       "rights": "Separate third-party rights; see RENDER-NOTICE.md"}
        subprocess.run(["g++", "-std=c++17", "-I" + str(args.lvgl_include.resolve()),
                        "-I" + str(COMPONENT), '-DLV_CONF_PATH="' + str(args.lvgl_config.resolve()) + '"',
                        str(temporary / "render.cpp"), str(args.lvgl_library.resolve()),
                        "-lm", "-o", str(temporary / "render")], check=True)
        result = subprocess.check_output(command, cwd=temporary, text=True)
        images = {}
        for line in result.splitlines():
            if not line.startswith("snapshot "):
                continue
            _, name, width, height, stride = line.split()
            image = Image.frombytes("RGB", (int(width), int(height)),
                                    (temporary / name).read_bytes(), "raw", "BGR", int(stride), 1)
            path = output / (Path(name).stem + ".png")
            image.save(path, optimize=True)
            images["docs/images/" + path.name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "width": image.width, "height": image.height,
                "kind": "synthetic-native-lvgl-desktop-render",
            }
        assert set(images) == {"docs/images/profiles.png", "docs/images/workout.png"}
        if artwork:
            images["docs/images/workout.png"]["exercise_artwork"] = artwork
        provenance = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in [COMPONENT / "gym_native.cpp", COMPONENT / "gym_native.h",
                                   COMPONENT / "workout_ui.cpp", ROOT / "tools/readme_fixture.cpp",
                                   ROOT / "tools/render_readme.py", ROOT / "native/server.py", COMPONENT / "ui_text.h"]}
        (output / "manifest.json").write_text(json.dumps({"schema": 1, "images": images,
            "source_hashes": provenance, "real_user_data_in_synthetic_renders": False,
            "authorized_real_photo_included": False,
            "hardware_framebuffer_capture": False,
            "language": args.language, "network_access": False, "restricted_exercise_media_visible": bool(artwork),
            "standalone_restricted_media_included": False}, indent=2) + "\n")
        print("Rendered two offline native-LVGL views with example data; review before publishing.")


if __name__ == "__main__":
    main()
