import sys, math
sys.path.insert(0, '/home/starlight/Projects/dusky-cursor-magic')
import numpy as np, cairo
import shader_soul as S

C = 220
a = S.Aura(C, 34.0, 1.0, 0.0)
st = S.Stars()
st.burst(0.0, 110, 110)                                  # click burst at orb
for i in range(6):                                       # trail behind
    st.shed(-0.05 * i - 0.02, 110 + 30 + i * 22, 110 + i * 9)
buf = np.zeros((a.F, a.F), np.uint32)
a.render(0.4, 0.5, 0.6, [(0, 0, 0.1, 1.0)], buf, core=True,
         stars=st.live(0.4, (0.0, 0.0), C / 2.0))
surf = cairo.ImageSurface.create_for_data(buf.view(np.uint8), cairo.FORMAT_ARGB32, a.F, a.F)
big = cairo.ImageSurface(cairo.FORMAT_ARGB32, C, C)
cr = cairo.Context(big)
cr.scale(2, 2)
cr.set_source_surface(surf, 0, 0)
cr.paint()
big.write_to_png('/tmp/soul_stars.png')
print('saved /tmp/soul_stars.png')
