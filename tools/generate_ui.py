#!/usr/bin/env python3
"""Generate the fixed 1280x800 LVGL layout, with a reviewable geometry manifest."""
import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]
widgets=[]; bounds=[]
def label(id,text,x,y,w,h,font,color='0xF1F5F9',align=None):
    d={'id':id,'text':text,'x':x,'y':y,'width':w,'height':h,'text_font':font,'text_color':color,'long_mode':'DOT'}
    if align:d['text_align']=align
    widgets.append({'label':d});bounds.append({'id':id,'x':x,'y':y,'w':w,'h':h,'kind':'label'})
def button(id,text,x,y,w,h,action,green=False,label_id=None):
    inner={'text':text,'align':'CENTER','text_font':'f26'}
    if label_id:inner['id']=label_id
    d={'id':id,'x':x,'y':y,'width':w,'height':h,'bg_color':'0x78E0B0' if green else '0x24344B','text_color':'0x10241D' if green else '0xF1F5F9','radius':16,'border_width':0,'shadow_width':0,'outline_width':0,'pad_all':0,'on_click':[{'lambda':action}],'widgets':[{'label':inner}]}
    widgets.append({'button':d});bounds.append({'id':id,'x':x,'y':y,'w':w,'h':h,'kind':'button'})
label('brand','OpenGym',32,32,300,50,'f36','0x78E0B0')
label('date','',850,40,398,42,'f26',align='RIGHT')
for i,t in enumerate(['Man','Tir','Ons','Tor','Fre','Lør','Søn']):button('day'+str(i),t,32+i*176,110,160,64,f'id(gym).select_day({i});')
label('eyebrow','ANDRE · UKEPLAN',32,206,1216,28,'f20','0x9BAFC8')
label('routine','Kobler til OpenGym …',32,235,1216,84,'f36')
label('position','',32,325,845,34,'f26','0x78E0B0')
label('exercise','',32,370,830,104,'f38')
label('target','',32,485,300,85,'f66')
label('load','',345,510,505,58,'f32','0xD6E4F5')
label('detail_label','',32,575,845,32,'f20','0xB2C2D7')
label('note','',32,609,845,43,'f20','0xB2C2D7')
label('timer_heading','PAUSE',920,340,328,34,'f20','0x9BAFC8','CENTER')
label('timer','00:00',900,386,368,98,'f76',align='CENTER')
button('minus','−15 s',920,500,156,60,'id(gym).timer_adjust(-15);')
button('plus','+15 s',1092,500,156,60,'id(gym).timer_adjust(15);')
button('timer_start','Start pause',920,578,328,74,'id(gym).timer_toggle();',True,'timer_action')
button('timer_reset','Nullstill',920,672,328,70,'id(gym).timer_reset();')
button('prev','‹ Forrige',32,672,180,70,'id(gym).navigate(-1);')
button('next','Neste ›',228,672,180,70,'id(gym).navigate(1);')
label('status','Kobler til …',32,764,860,28,'f20','0x9BAFC8')
label('log_hint','Logging i OpenGym',920,764,328,28,'f20','0x9BAFC8','RIGHT')
fonts=[{'file':'fonts/DejaVuSans.ttf','id':'f'+str(n),'size':n,'bpp':4,'glyphsets':['GF_Latin_Core'],'glyphs':['‹','›','−','…','×','·']} for n in [20,26,32,36,38,66,76]]
config={'font':fonts,'lvgl':{'id':'gym_ui','displays':['panel_display'],'touchscreens':[{'touchscreen_id':'panel_touch'}],'rotation':90,'color_depth':16,'buffer_size':'100%','byte_order':'little_endian','text_font':'f26','bg_color':'0x101927','text_color':'0xF1F5F9','pages':[{'id':'main_page','bg_color':'0x101927','pad_all':0,'scrollable':False,'widgets':widgets}]}}
# JSON is a strict subset of YAML, making generated escaping unambiguous.
(P/'firmware/ui.yaml').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
(P/'docs/layout.json').write_text(json.dumps({'width':1280,'height':800,'rotation':90,'widgets':bounds},indent=2)+'\n')
for w in bounds:assert 0<=w['x'] and 0<=w['y'] and w['x']+w['w']<=1280 and w['y']+w['h']<=800,w
print(f'{len(bounds)} visible widget bounds checked')
