// Genera clips de prueba con canal alfa (varios códecs) para ver cuál acepta CapCut.
//   node alpha_test.mjs [escena] [desde] [hasta]
import fs from 'node:fs'; import path from 'node:path'; import { execFileSync } from 'node:child_process';
import { ROOT, FFMPEG, startServer, launch, openScene } from './lib/harness.mjs';
const [scene = '01-balance', from = '5', to = '8.5'] = process.argv.slice(2);
const dir = path.join('/tmp', 'alpha_frames'); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
const server = await startServer(); const browser = await launch();
const { page, cdp } = await openScene(browser, server, scene, 'alfa');
await cdp.send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
let n = 0;
for (let t = +from; t < +to; t += 1 / 60) {
  await page.evaluate((t) => window.__seek(t), t);
  const r = await cdp.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(path.join(dir, `a_${String(n++).padStart(5, '0')}.png`), Buffer.from(r.data, 'base64'));
}
await browser.close(); server.close();
const out = path.join(ROOT, 'renders', 'alfa-test'); fs.mkdirSync(out, { recursive: true });
const I = ['-framerate', '60', '-i', path.join(dir, 'a_%05d.png')];
const run = (name, a) => { execFileSync(FFMPEG, ['-y', '-loglevel', 'error', ...I, ...a, path.join(out, name)]); console.log('✔', name, (fs.statSync(path.join(out, name)).size / 1e6).toFixed(1), 'MB'); };
run('1_prores4444.mov', ['-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', '-vendor', 'apl0']);
run('2_webm_vp9.webm', ['-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-crf', '18', '-b:v', '0', '-row-mt', '1', '-auto-alt-ref', '0']);
run('3_webm_vp8.webm', ['-c:v', 'libvpx', '-pix_fmt', 'yuva420p', '-b:v', '20M', '-auto-alt-ref', '0']);
run('4_qtrle.mov', ['-c:v', 'qtrle', '-pix_fmt', 'argb']);
run('5_png.mov', ['-c:v', 'png', '-pix_fmt', 'rgba']);
// control visual: primer ProRes sobre damero
execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0xff3b8b:s=1920x1080', '-ss', '2.5', '-i', path.join(out, '1_prores4444.mov'), '-filter_complex', '[0][1]overlay', '-frames:v', '1', path.join(ROOT, 'stills', 'alfa_check.png')]);
console.log('frames:', n);
