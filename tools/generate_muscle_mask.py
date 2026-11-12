from pathlib import Path
import json, io
from itertools import groupby
import cairosvg
from PIL import Image
p=Path(__file__).resolve().parents[1]
source=p/'vendor/opengym/frontend/src/lib/body-paths.js'
data=json.loads(source.read_text().split('export default ',1)[1].strip().rstrip(';'))
muscles=['trapezius','deltoids','chest','upper-back','serratus','biceps','triceps','forearm','abs','obliques','lower-back','gluteal','quadriceps','hamstring','adductors','hip-flexors','calves','tibialis']
canvas=Image.new('RGB',(384,320),(0,0,0))
for i,view in enumerate(['front','back']):
    shape=data['male'][view]
    paths=[]
    for part,segments in shape['p'].items():
        index=muscles.index(part)+2 if part in muscles else 1
        for d in segments:
            paths.append(f'<path fill="#{index:02x}0000" d="{d}"/>')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{shape["vb"]}" shape-rendering="crispEdges">'+''.join(paths)+'</svg>'
    raster=Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(),output_width=182,output_height=320))).convert('RGB')
    canvas.paste(raster,(i*202,0))
values=[r for r,g,b in canvas.getdata()]
assert max(values)==19
runs=[(sum(1 for _ in group),value) for value,group in groupby(values)]
assert sum(n for n,v in runs)==384*320
header='''// Generated from OpenGym body-paths.js / MuscleMap (Melih Colpan, MIT).
// Geometry only, no exercise media. See docs/MUSCLE-VOLUME-EQUIPMENT.md.
#pragma once
#include <cstdint>
namespace esphome::gym_native {
struct MuscleRun { uint16_t count; uint8_t part; };
inline constexpr MuscleRun MUSCLE_RUNS[] = {
'''
header+=''.join('  '+', '.join('{%d, %d}'%x for x in runs[i:i+8])+',\n' for i in range(0,len(runs),8))
header+='};\n}  // namespace esphome::gym_native\n'
(p/'firmware/custom_components/gym_native/muscle_mask.h').write_text(header)
# No generated preview or local credential is part of the release.
print(len(runs),'RLE spans, maxrun',max(n for n,v in runs))
