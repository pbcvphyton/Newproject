const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright-core');

const HTML = '/home/user/Newproject/eyescan/dist/index.html';
const FACE = '/tmp/claude-0/-home-user-Newproject/b0824a4c-0fe3-5110-99c1-e7b39702f39e/scratchpad/face_big.png';
const SHOT_DIR = '/tmp/claude-0/-home-user-Newproject/b0824a4c-0fe3-5110-99c1-e7b39702f39e/scratchpad';

// CSP de pior caso plausível para o hosting de artefatos:
const CSP = "default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data:; media-src 'self' blob:; font-src data:";

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': CSP });
  fs.createReadStream(HTML).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(8944, r));
  const browser = await chromium.launch({
    executablePath: '/opt/pw-browsers/chromium',
    headless: true,
    args: ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  });
  const ctx = await browser.newContext({ permissions: ['camera'], viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

  console.log('== carregando app ==');
  await page.goto('http://localhost:8944/', { waitUntil: 'domcontentloaded' });

  // espera o motor ficar pronto
  await page.waitForFunction(() => document.getElementById('engineTxt').textContent.includes('pronto'), null, { timeout: 90000 });
  console.log('motor:', await page.textContent('#engineTxt'));
  console.log('bootlog:\n' + (await page.textContent('#bootlog')));

  // ---------- modo foto ----------
  console.log('\n== modo foto (astronauta) ==');
  await page.setInputFiles('#fileInput', FACE);
  await page.waitForTimeout(4000);
  console.log('stageMsg:', await page.evaluate(() => {
    const el = document.getElementById('stageMsg');
    return el.classList.contains('hidden') ? '(oculto)' : el.textContent;
  }));
  console.log('--- card OD ---'); console.log((await page.textContent('#cardOD')).replace(/\s+/g,' '));
  console.log('--- card OE ---'); console.log((await page.textContent('#cardOE')).replace(/\s+/g,' '));
  console.log('--- impressão ---'); console.log((await page.textContent('#impressao')).replace(/\s+/g,' '));
  console.log('--- qualidade ---'); console.log((await page.textContent('#quality')).replace(/\s+/g,' '));
  await page.screenshot({ path: SHOT_DIR + '/shot_photo.png' });

  // ---------- modo câmera (dispositivo falso: sem rosto) ----------
  console.log('\n== modo câmera (fake device) ==');
  await page.click('#btnCam');
  await page.waitForTimeout(3500);
  console.log('stageMsg:', await page.evaluate(() => {
    const el = document.getElementById('stageMsg');
    return el.classList.contains('hidden') ? '(oculto)' : el.textContent;
  }));
  await page.screenshot({ path: SHOT_DIR + '/shot_live.png' });

  console.log('\n== erros de console ==');
  console.log(errors.length ? errors.slice(0, 12).join('\n') : '(nenhum)');

  await browser.close();
  server.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
