# Periocular+ — triagem visual de ptose & dermatocalásio pela câmera

Aplicativo web de arquivo único (`dist/index.html`) que abre a câmera frontal,
localiza os olhos com uma malha facial de 478 landmarks (MediaPipe Face
Landmarker, com íris) e calcula, **em milímetros**, os índices clínicos usados
na avaliação de ptose palpebral e de candidatura à blefaroplastia — pintando
cada achado sobre a imagem com código de cores por severidade.

> **Aviso**: protótipo educacional de visão computacional. Não é dispositivo
> médico, não gera diagnóstico e não substitui avaliação presencial por
> oftalmologista ou cirurgião oculoplástico.

## A medicina, explicada para quem vai manter o código

**A régua anatômica.** Não há como medir milímetros numa foto sem uma
referência de escala. A saída clássica da oftalmologia computacional: o
diâmetro horizontal da íris adulta (HVID) é notavelmente constante entre
humanos — 11,7 ± 0,5 mm. O app mede a íris em pixels (landmarks 469↔471 e
474↔476) e obtém `px/mm`. Tudo o mais deriva disso.

**MRD-1 (margin reflex distance 1)** — do centro pupilar à margem da pálpebra
superior. É *a* medida da ptose: ≥ 4 mm típico; 3–4 leve; 2–3 moderada;
< 2 acentuada. O centro pupilar vem do landmark central da íris (468/473); a
margem, da interpolação da polilinha do cílio superior na abscissa da pupila.

**MRD-2** — do centro pupilar à margem inferior (~5 mm). Alto = retração /
"scleral show" (esclera aparente sob a íris); baixo = pálpebra inferior alta
(cuidado: sorrir eleva a pálpebra inferior — por isso o app pede expressão
neutra via blendshapes).

**Exposição pré-tarsal** — faixa de pálpebra visível entre os cílios e a dobra
de pele (fileira de landmarks da dobra vs. fileira da margem). Quando a dobra
avança sobre os cílios (< ~1,5 mm), é o sinal cardinal de **dermatocalásio**
— o excesso de pele que a blefaroplastia superior remove. É a área que o app
pinta sobre a pálpebra, verde → âmbar → vermelho.

**Margem → supercílio** — distância da margem palpebral à fileira *inferior*
de landmarks do supercílio, no eixo pupilar. Importante: essa fileira da malha
fica abaixo do pelo da sobrancelha (próxima ao rebordo orbitário), então os
limiares do código (~8 mm) foram calibrados para a fileira, e **não** são a
distância clínica medida com régua (~15–20 mm). Supercílio caído "empurra"
pele sobre o olho — às vezes o tratamento certo é browlift, não blefaroplastia.

**Tilt cantal** — inclinação do eixo cantal (canto externo vs. interno).
+2° a +8° é o padrão estético; negativo dá o aspecto de olhar "caído".

**Higiene de medição.** Medidas só entram na média (mediana móvel de 15
frames) quando a captura passa nos portões de qualidade: íris ≥ 18 px
(distância), roll ≤ 7° (cabeça reta — todas as coordenadas são rotacionadas
pelo eixo interocular antes de medir), razão de largura dos olhos (proxy de
yaw), olhos abertos, sem sorriso e testa relaxada (blendshapes).

## A engenharia

- **Zero rede em runtime.** O WASM do MediaPipe (9 MB) e o modelo
  `face_landmarker.task` (3,7 MB) vão embutidos no HTML como gzip+base64,
  descompactados com `DecompressionStream`. O runtime é enganado de propósito:
  `wasmLoaderPath: ''` faz o `FilesetResolver` pular o `<script src>` externo
  (o loader já foi inlined e define `self.ModuleFactory`), e
  `self.Module = { wasmBinary }` + `baseOptions.modelAssetBuffer` eliminam os
  `fetch`. Resultado: funciona sob CSP `default-src 'none'` (só exige
  `'unsafe-inline'` e `'wasm-unsafe-eval'` em `script-src`).
- **GPU com fallback.** Tenta o delegate GPU (WebGL2); se falhar, recria em
  CPU (XNNPACK). Nota: o runtime zera `self.ModuleFactory` após o uso — o
  código guarda a referência para conseguir tentar de novo.
- **Espelhamento sem texto invertido.** O `<video>` é espelhado via CSS
  (selfie natural), mas o canvas de overlay espelha só as coordenadas
  (`x → W − x`) na hora de desenhar, então rótulos e números ficam legíveis.
  Fotos carregadas não são espelhadas.
- **Modo foto.** Fallback completo quando `getUserMedia` não está disponível
  (iframe sem permissão de câmera, etc.): `FileReader` → data-URI → canvas →
  mesmo pipeline (`detectForVideo` aceita canvas como fonte de textura).

## Build

```bash
cd eyescan
# assets (não versionados) — origem npm/Google, uma vez só:
curl -sSL https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-0.10.14.tgz | tar -xz -C /tmp
cp /tmp/package/wasm/vision_wasm_internal.{js,wasm} /tmp/package/vision_bundle.cjs assets/
curl -sSL -o assets/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

node build.mjs          # → dist/index.html (~8,3 MB, auto-contido)
```

Abra `dist/index.html` em qualquer navegador moderno (Chrome/Edge/Safari 16.4+).
Câmera exige HTTPS ou `localhost`; o modo foto funciona até em `file://`.

## Teste automatizado

`test/e2e.js` (na raiz do histórico da sessão) serve o `dist/` sob o CSP mais
restritivo plausível e valida com Chromium headless: boot do motor, análise de
uma foto de rosto real (medidas fisiológicas: MRD-1 ≈ 4,3 mm), portões de
qualidade (detecção de sorriso) e o modo câmera com dispositivo fake.
