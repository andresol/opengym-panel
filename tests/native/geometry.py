"""Audit literal native page geometry directly from the C++ construction calls.

Dynamic exercise/set/person children intentionally scroll in bounded inner boxes.
This is a source geometry check, NOT an LVGL rendering or a physical screenshot.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'firmware/custom_components/gym_native/gym_native.cpp').read_text()
begin = source.split('void GymNative::begin(', 1)[1].split('bool GymNative::accept_people(', 1)[0]
parents = {'root_': (1280, 800)}
observed = []
rectangles = {}
origins = {'root_': (0, 0)}
for line in begin.splitlines():
    match = re.search(r'(?:auto \*(\w+)|([\w\[\]]+))\s*=\s*(box|label|button)\((.*)\);', line)
    unnamed = re.search(r'^\s*(label)\((.*)\);', line)
    if not match and not unnamed:
        continue
    name, kind, raw = ((match[1] or match[2]), match[3], match[4]) if match else ('label', unnamed[1], unnamed[2])
    # All call strings here contain no embedded commas. Remove strings before splitting.
    args = re.sub(r'"(?:\\.|[^"\\])*"', 'TEXT', raw).split(',')
    parent = args[0].strip()
    offset = 1 if kind == 'box' else 2
    if parent not in parents:
        raise AssertionError('Unresolved parent ' + parent)
    variants = range(7) if name == 'days_[n]' else range(2) if name == 'line' else [0]
    for n in variants:
        values = [int(eval(a, {'__builtins__': {}}, {'n': n, 'column': n})) for a in args[offset:offset + 4]]
        x, y, w, h = values
        pw, ph = parents[parent]
        assert x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= pw and y + h <= ph, (name, parent, values, parents[parent])
        observed.append((name, parent, values))
        ox, oy = origins[parent]
        rectangles[name] = (ox + x, oy + y, w, h)
    if kind == 'box':
        parents[name] = (w, h)
        origins[name] = (ox + x, oy + y)
assert len(observed) >= 40, len(observed)
assert parents['workout_'] == (1280, 680)
assert parents['media_stage_'] == (640, 360)
# Navigation and pause keep their approved bottom edge; the exercise list now
# reaches the same edge in the column freed by moving Start to the header.
footer = [rectangles[name] for name in ['controls_[0]', 'controls_[1]', 'timer_button_']]
assert footer == [(336, 712, 264, 64), (624, 712, 264, 64), (956, 712, 300, 64)]
assert all(y + h == 800 - 24 for x, y, w, h in footer)
assert rectangles['timer_label_'] == (956, 568, 204, 54)
assert rectangles['pause_caption'] == (1172, 580, 84, 30)
assert rectangles['pause_caption'][0] - sum(rectangles['timer_label_'][::2]) == 12
assert 'lv_obj_set_style_text_align(timer_label_, LV_TEXT_ALIGN_LEFT, 0)' in begin
assert 'lv_obj_set_style_text_align(pause_caption, LV_TEXT_ALIGN_RIGHT, 0)' in begin
assert 1280 - (footer[-1][0] + footer[-1][2]) == 24
assert rectangles['person_button'] == (956, 24, 300, 64)
assert rectangles['person_button'][2:] == rectangles['timer_button_'][2:]
assert rectangles['exercise_list_'] == (24, 196, 260, 580)
assert rectangles['exercise_list_'][1] + rectangles['exercise_list_'][3] == 800 - 24
assert rectangles['exercise_more_'] == (24, 748, 260, 24)
assert 'exercise_more_ = label(workout_, "↓", 24, 652, 260, 24, normal_, MUTED)' in begin
assert 'lv_obj_set_style_text_align(exercise_more_, LV_TEXT_ALIGN_CENTER, 0)' in begin
# The passive footer has its own reserved space, never covers a touch tile and
# disappears at the real scroll bottom. Short lists keep the full viewport.
assert 'content_height > available_height ? 36 : 0' in source
assert '100 + available_height - 28' in source
assert 'LV_EVENT_SCROLL, this' in begin
assert 'lv_obj_get_scroll_bottom(exercise_list_) <= 0' in source
for available in [500, 580]:
    for count in [0, 1, 5, 6, 7, 9, 40]:
        content = max(0, (count - 1) * 85 + 70) if count else 0
        overflow = content > available
        height = available - (36 if overflow else 0)
        hint_y = 100 + available - 28
        assert hint_y + 24 <= 100 + available
        if overflow:
            assert hint_y - (100 + height) == 8
        else:
            assert height == available
assert rectangles['note_scroller_'][1] + rectangles['note_scroller_'][3] + 28 == footer[0][1]
assert rectangles['session_button_'] == (336, 24, 552, 64)
# The image, not the 640 px invisible stage, anchors both control rows.
workflow = (ROOT / 'firmware/custom_components/gym_native/workout_ui.cpp').read_text()
assert 'image_display_width_ = rendered_width' in source
assert 'const int left = image_left - 20' in workflow
assert 'const int span = image_display_width_ + 40' in workflow
assert 'const int first_width = (span - 24) / 2' in workflow
assert 'const int second_left = left + first_width + 24' in workflow
assert 'const int action_width = active ? first_width : span' in workflow
assert 'lv_obj_set_x(session_button_, left)' in workflow
assert 'lv_obj_set_width(session_text_, action_width - 16)' in workflow
assert 'resize_second(set_button_)' in workflow and 'resize_second(controls_[1])' in workflow
assert 'lv_obj_set_x(controls_[0], left)' in workflow
assert rectangles['set_button_'] == (624, 24, 264, 64)
assert rectangles['session_button_'][0] == footer[0][0]
assert rectangles['session_button_'][0] + rectangles['session_button_'][2] == footer[1][0] + footer[1][2]
assert footer[1][0] - (footer[0][0] + footer[0][2]) == 24
assert rectangles['person_button'][0] + rectangles['person_button'][2] == footer[2][0] + footer[2][2]
assert 'lv_obj_set_width(person_button_' not in begin
assert 'lv_obj_set_x(person_button_' not in begin
# Both validated media formats have the same centre and exactly 20 px overflow.
stage_x, _, stage_width, _ = rectangles['media_stage_']
for drawn_width, expected_left, expected_span in [(512, 336, 552), (512, 336, 552)]:
    image_left = stage_x + (stage_width - drawn_width) // 2
    left, span = image_left - 20, drawn_width + 40
    first = (span - 24) // 2
    second_left, second = left + first + 24, span - 24 - first
    assert (left, span) == (expected_left, expected_span)
    assert left + span // 2 == image_left + drawn_width // 2 == 612
    assert image_left - left == left + span - (image_left + drawn_width) == 20
    assert second_left - (left + first) == 24 and first == second
    assert first >= 248 and left >= 268 + 24 and left + span <= 956 - 24
assert all(rectangles[name][3] == 64 for name in ['session_button_', 'set_button_', 'person_button', 'timer_button_', 'controls_[0]', 'controls_[1]'])
assert rectangles['brand_label_'] == (24, 24, 244, 36)
assert rectangles['date_label_'] == (24, 64, 148, 24)
assert 'lv_obj_set_style_text_font(session_text_, heading_' not in begin
assert 'lv_obj_set_style_text_font(timer_text_, heading_' not in begin
# Seven original-size tiles with 15 px gaps end exactly at the bottom margin;
# the eighth does not leave a thin clipped border at the initial scroll position.
assert 6 * 85 + 70 == parents['exercise_list_'][1]
assert 4 * 38 + 36 <= parents['rows_'][1]
assert 'i * 85, 260, 70, 4, i' in source
assert 'lv_obj_set_width(caption, 228)' in source
assert 'owner_label_' not in source
assert 'set_text(date_label_, display_date)' in source
assert 'lv_obj_set_style_border_width(person_button, 2, 0)' in begin
assert begin.index('workout_ = box(') < begin.index('session_button_ = button(')
assert 'lv_obj_set_style_pad_all(root_, 0, 0)' in begin
assert 'lv_obj_remove_flag(root_, LV_OBJ_FLAG_SCROLLABLE)' in begin
assert (ROOT / 'firmware/custom_components/gym_native/timer.h').read_bytes() == (ROOT / 'firmware/custom_components/gym_panel/timer.h').read_bytes()
print(f'{len(observed)} native geometry bounds passed; dynamic lists scroll inside bounded parents')

# Centre date beneath visible OpenGym text; the old invisible box is not the anchor.
assert 'lv_obj_set_width(brand_label_, LV_SIZE_CONTENT)' in begin
assert 'lv_obj_set_width(date_label_, lv_obj_get_width(brand_label_))' in begin
assert 'lv_obj_set_style_text_align(date_label_, LV_TEXT_ALIGN_CENTER, 0)' in begin
assert 'lv_obj_set_style_text_font(caption, exercise_font_, 0)' in source
cfg = (ROOT / 'firmware/opengym-v3.yaml').read_text()
assert 'id: f18\n    size: 18' in cfg and 'id(f18)->get_lv_font()' in cfg
# Photo-led correction: no outer frame or vertical rules. Only separators
# between real rows; each label is centred vertically using its measured height.
assert 'rows_frame_' not in source and 'rows_dividers_' not in source
assert 'rows_frame_' not in (ROOT / 'firmware/custom_components/gym_native/gym_native.h').read_text()
assert 'const int row_height = interactive ? 54 : 38' in source
for field,x in [('name',10),('load',102),('target',194)]:
    assert f'label(parent, {field}.c_str(), {x}, y, 90, row_height, small_)' in source
assert 'lv_obj_set_height(cell, LV_SIZE_CONTENT)' in source
assert 'lv_obj_set_y(cell, y + (row_height - height) / 2)' in source
assert 'lv_obj_set_style_text_align(cell, LV_TEXT_ALIGN_LEFT, 0)' in source
assert 'lv_obj_set_style_text_align(done_cell, LV_TEXT_ALIGN_LEFT, 0)' in source
assert 'group_top + name_height + 2' in source
assert 'if (row_y == 0) return' in source
assert 'box(rows_, 8, row_y - (interactive ? 4 : 0), 276, 1, 0x343a40)' in source
assert 'lv_obj_remove_flag(line, LV_OBJ_FLAG_CLICKABLE)' in source
assert 'divide_before(true)' in source and 'divide_before(false)' in source
assert 'button(rows_, "", 0, row_y, 292, 54, 12, i * 3 + side, is_next)' in source
assert 'columns(b, 0, e->rows[i].name' in source
tracks=[(8,92),(100,92),(192,92)]
assert tracks[0][0] == 292-sum(tracks[-1]) == 8
assert all(tracks[i+1][0]-tracks[i][0] == 92 for i in range(2))
assert [x+2 for x,w in tracks] == [10,102,194]
assert all(x+2+90 == x+w for x,w in tracks)
for row_height in [38,54]:
    for label_height in [19,38]:
        top=(row_height-label_height)//2
        assert top>=0 and abs(top-(row_height-top-label_height))<=1
assert (54-(19+2+19))//2 == 7
for count in [0,1,3,5,24,48]:
    for active in [False,True]:
        pitch,height=(62,54) if active else (38,38)
        separators=[n*pitch-(4 if active else 0) for n in range(1,count)]
        assert len(separators)==max(0,count-1)
        for n,y in enumerate(separators,1):
            assert (n-1)*pitch+height <= y <= n*pitch
            if active: assert y-((n-1)*pitch+height) == n*pitch-y == 4
        if count: assert all(0<y<(count-1)*pitch+height for y in separators)
print('Equal columns, measured vertical centring and row-only non-interactive dividers passed')

# Latest physical feedback: passive text needs 24 px side inset, but media and
# controls keep their approved geometry. Routine name is 12 px below baseline.
assert rectangles['position_label_'] == (316, 160, 592, 24)
assert rectangles['exercise_label_'] == (316, 196, 592, 72)
assert rectangles['note_scroller_'] == (316, 644, 592, 40)
assert rectangles['note_label_'][:3] == (316, 644, 592)
assert rectangles['routine_label_'] == (24, 108, 664, 48)
for name in ['position_label_', 'exercise_label_', 'note_scroller_']:
    x, _, w, _ = rectangles[name]
    assert x - stage_x == stage_x + stage_width - (x + w) == 24
    assert x - (rectangles['exercise_list_'][0] + rectangles['exercise_list_'][2]) == 32
assert rectangles['media_stage_'] == (292, 272, 640, 360)
assert rectangles['routine_label_'][1] - (64 + 24) == 20
print('Photo-led text inset and routine/date separation passed')

# Physical feedback: a fixed illustration canvas must anchor BOTH modes; an
# animation must never shrink Start, Register, Previous/Next or the touch area.
assert rectangles['media_viewport_'] == (356, 272, 512, 360)
assert 'lv_image_create(media_viewport_)' in begin
assert 'lv_obj_remove_flag(media_viewport_, LV_OBJ_FLAG_OVERFLOW_VISIBLE)' in begin
assert 'lv_obj_remove_flag(media_viewport_, LV_OBJ_FLAG_CLICKABLE)' in begin
assert 'hidden(media_viewport_, true)' in source
assert 'const int rendered_width = 512, rendered_height = 360' in source
assert 'playing_ ? 410 : 256' in source
assert 'playing_ ? 384 : 256' not in source
assert 'playing_ ? w * 3 / 2' not in source
for w,h,scale in [(512,360,256),(320,224,410)]:
    drawn_w,drawn_h=w*scale/256,h*scale/256
    assert abs(drawn_w-512)<1 and abs(drawn_h-360)<2
    assert max(0,(drawn_w-512)/2)<1  # only the source's white margin, not content
# Compact summary keeps font size; measured overflow gets two full-width values.
assert 'lv_text_get_size(&summary_size, summary.c_str(), heading_' in source
assert 'summary_size.x <= 300 && summary_size.y <= 42' in source
assert 'set_text(target_label_, compact ? summary : target)' in source
assert 'lv_obj_set_y(detail_label_, compact ? 164 : 208)' in source
assert 'lv_obj_set_y(rows_, compact ? 222 : 268)' in source
assert 'lv_obj_set_height(rows_, compact ? 240 : 194)' in source
assert 4*54+3*8==240
assert 222+240==268+194==462
assert 112+40<164 and 164+48+10==222
assert 462<484 and rectangles['timer_button_']==(956,712,300,64)
print('Fixed media envelope/control bounds and compact summary/fallback passed')

# One restrained completion glyph: correct font subset and a dedicated tile slot.
assert 'label(b, "✓", 220, 23, 24, 24, normal_, ACCENT)' in source
assert 'label(b, "Fullført"' not in source
assert 'is_next ? "NESTE" : "✓"' in source
assert 'is_next ? small_ : normal_' in source
assert 'lv_obj_set_width(name, complete ? 188 : 228)' in source
assert 'lv_obj_set_height(name, complete ? 46 : LV_SIZE_CONTENT)' in source
assert 'lv_obj_align(name, LV_ALIGN_LEFT_MID, 16, 0)' in source
assert 16+188+16 == 220 and 220+24+16 == 260
assert 2*22+1 <= 46 and (70-46)//2 == 12
assert 23+24//2 == 70//2
font20=cfg.split('id: f20',1)[1].split('  - file:',1)[0]
assert "'✓'" in font20
assert "'↓'" in font20
for role in ['f16','f18','f30','f42']:
    assert "'✓'" not in cfg.split('id: '+role,1)[1].split('  - file:',1)[0].split('lvgl:',1)[0]
print('Single completion glyph, dedicated tile slot and exact font subset passed')
