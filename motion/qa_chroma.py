"""Control de calidad del chroma key.

  python3 qa_chroma.py renders/01-balance_VERDE.mp4

1) Mide cuántos píxeles "sucios" hay (mezclas con el verde que no son verde puro
   ni el borde normal de antialiasing) en frames de muestra.
2) Genera stills/<nombre>_KEYTEST.png: el video recortado con chromakey (como lo
   haría CapCut) encima de un fondo de prueba cálido, para ver bordes y halos.
"""
import subprocess, sys, os
import numpy as np
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
src = sys.argv[1]
name = os.path.splitext(os.path.basename(src))[0]
os.makedirs('stills', exist_ok=True)

# duración
probe = subprocess.run([FF, '-i', src], capture_output=True, text=True).stderr
dur = next(l for l in probe.splitlines() if 'Duration' in l).split('Duration: ')[1].split(',')[0]
h, m, s = dur.split(':'); dur = int(h) * 3600 + int(m) * 60 + float(s)

W, H = 1920, 1080
worst = 0
for k in range(1, 12):
    t = dur * k / 12
    raw = subprocess.run([FF, '-v', 'error', '-ss', f'{t:.3f}', '-i', src, '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    pure = (g > 200) & (r < 60) & (b < 60)
    greenish = (g > r + 50) & (g > b + 50) & ~pure            # mezcla con verde
    # tolerancia: bordes de 1–2 px alrededor de los elementos
    import numpy.lib.stride_tricks as st
    nonpure = ~pure
    pad = np.pad(nonpure & ~greenish, 2)
    near = np.zeros_like(nonpure)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near |= pad[2 + dy:2 + dy + H, 2 + dx:2 + dx + W]
    dirty = greenish & ~near
    pct = 100 * dirty.mean()
    worst = max(worst, pct)
    print(f't={t:5.2f}s  verde puro {100*pure.mean():5.1f}%  mezcla fuera de bordes {pct:.4f}%')
print('PEOR:', f'{worst:.4f}%', '(ideal < 0.05%)')

# composición de prueba
t = dur * 0.6
out = f'stills/{name}_KEYTEST.png'
subprocess.run([FF, '-y', '-v', 'error',
                '-f', 'lavfi', '-i', 'gradients=s=1920x1080:c0=0x8a5a3c:c1=0xd9b38c:c2=0x5a6b7a:n=3:speed=0',
                '-ss', f'{t:.3f}', '-i', src,
                '-filter_complex', '[1:v]chromakey=0x00FF00:0.18:0.06,despill=type=green[k];[0:v][k]overlay=format=auto',
                '-frames:v', '1', out], check=True)
print('prueba de recorte:', out)
