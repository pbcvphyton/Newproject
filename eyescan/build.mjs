#!/usr/bin/env node
/**
 * Gera dist/index.html — um único arquivo auto-contido:
 *   - runtime MediaPipe tasks-vision (JS inline)
 *   - vision_wasm_internal.wasm  (gzip + base64)
 *   - face_landmarker.task       (gzip + base64)
 *
 * Assets esperados em ./assets (veja README.md para as URLs de download).
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const A = f => join(root, 'assets', f);

const needed = ['vision_wasm_internal.js', 'vision_wasm_internal.wasm',
                'vision_bundle.cjs', 'face_landmarker.task'];
for (const f of needed){
  if (!existsSync(A(f))){
    console.error(`Asset ausente: assets/${f} — veja eyescan/README.md (seção "Build").`);
    process.exit(1);
  }
}

const gzb64 = f => gzipSync(readFileSync(A(f)), { level: 9 }).toString('base64');

let html = readFileSync(join(root, 'src', 'app.template.html'), 'utf8');
html = html
  .replace('__B64GZ_WASM__',  () => gzb64('vision_wasm_internal.wasm'))
  .replace('__B64GZ_MODEL__', () => gzb64('face_landmarker.task'))
  .replace('__WASM_LOADER_JS__',    () => readFileSync(A('vision_wasm_internal.js'), 'utf8'))
  .replace('__VISION_BUNDLE_CJS__', () => readFileSync(A('vision_bundle.cjs'), 'utf8'));

mkdirSync(join(root, 'dist'), { recursive: true });
const out = join(root, 'dist', 'index.html');
writeFileSync(out, html);
console.log(`ok: ${out} (${(html.length/1048576).toFixed(1)} MB)`);
