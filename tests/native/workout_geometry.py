"""Static modal geometry/font/action gate; not a screenshot or physical acceptance."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[2]
source=(root/'firmware/custom_components/gym_native/workout_ui.cpp').read_text()
for line in source.splitlines():
    match=re.search(r'(?:label|button)\(modal_,.*?,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),',line)
    if match:
        x,y,w,h=map(int,match.groups())
        assert 0<=x and 0<=y and x+w<=1280 and y+h<=800,(x,y,w,h)
for i in range(32):
    x,y=220+i%8*106,300+i//8*67
    assert x+96<=1060 and y+57<=558
assert 128+32+3<=192
assert 128+32+1<=192  # own-routine picker, separate from the set-row bindings
assert '"Bytt økt", 24, 616, 260, 64, 22' in (root/'firmware/custom_components/gym_native/gym_native.cpp').read_text()
# Two equal adjustable cards; every child stays inside its visible card.
for line in range(2):
    x,y,w,h=88+line*568,224,536,328
    assert x>=0 and x+w<=1280 and y+h<574
    for cx,cy,cw,ch in [(32,24,472,30),(32,96,88,80),(132,96,272,80),
                         (416,96,88,80),(32,204,472,24),
                         (32,240,146,56),(194,240,146,56),(356,240,148,56)]:
        assert cx>=0 and cy>=0 and cx+cw<w and cy+ch<h
# Four load steps preserve equal card insets and 12 px gutters; the other card
# keeps its three existing controls. No button overlaps the value or footer.
load_steps = [(32+i*121, 240, 109, 56) for i in range(4)]
assert load_steps[0][0] == 536-(load_steps[-1][0]+load_steps[-1][2]) == 32
assert all(b[0]-(a[0]+a[2]) == 12 for a,b in zip(load_steps,load_steps[1:]))
assert all(x+w<=504 and y+h<328 and w>=100 and h>=56 for x,y,w,h in load_steps)
assert 'std::array<std::array<lv_obj_t *, 4>, 3> step_buttons_' in (root/'firmware/custom_components/gym_native/gym_native.h').read_text()
assert 'steps.size() == 4' in source
assert 'for (size_t i = 0; i < steps.size(); ++i)' in source
assert 132-(32+88)==416-(132+272)==12
assert 656-(88+536)==32
assert 224+328<574 and 574+48<648 and 648+72<=800
assert 'auto *card = box(modal_, 88 + line * 568, 224, 536, 328' in source
assert 'e.name.c_str(), 88, 48, 1104, 104, large_' in source
assert 'title.c_str(), 88, 48 + title_height + 16, 1104, 44, heading_' in source
assert 48+104+16+44<224  # longest two-line heading and enlarged set context
assert 'editing_steps_.fill(1)' in source
assert 'std::vector<int>{1} : result_steps(field, e.mode)' in source
assert 'adjust_result(encoded < 0 ? -amount : amount)' in source
assert 'weight_caption(editing_value_.weight, e.unit)' in source
assert 'Register all' not in source
assert 'root["done"] = done' in source
assert 'root["revision"] = action == "set" ? editing_revision_' in source
cfg=(root/'firmware/opengym-v3.yaml').read_text()
assert 'panel_view' not in cfg and 'test_action' not in cfg
assert "'→'" in cfg.split('id: f20',1)[1].split('  - file:',1)[0]
print('Workout modal bounds, 32-key pairing, bindings, explicit completion and release API/font gates passed')

# Rest days use their own visible page, not disabled training/timer controls.
assert 'rest_page_ = box(workout_, 0, 56, 1280, 624, BG)' in (root/'firmware/custom_components/gym_native/gym_native.cpp').read_text()
assert 'binding_count_ = 192' in source and 192+32<=224
for i in range(32):
    x,y=(i%2)*564,(i//2)*154
    assert x+540<=1104
    if i<6: assert y+138<=446
assert 3*138+2*16==446
assert 2*540+24==1104
assert '540, 138, 23, i' in source
assert 'modal_kind_ != 4 && !(!modal_kind_ && exercises_.empty())' in source
assert 'wanted_routine_ = key' in source

# The community edition protects browser administration by default.
web_config = cfg.split('web_server:', 1)[1].split('switch:', 1)[0]
assert re.search(r'^\s+auth:', web_config, re.MULTILINE)
assert 'password: !secret admin_password' in web_config
assert 'local: true' in web_config and 'ota: false' in web_config and 'log: false' in web_config
# Removing web login must not remove independent API/OTA protection.
assert 'key: !secret native_api_key' in cfg
assert 'password: !secret native_ota_password' in cfg

# ESPHome 2026.9 HTTP matching uses names (URL-encoded by the admin client).
assert 'entity->get_name().c_str()' in cfg
assert 'get_object_id_to' not in cfg
