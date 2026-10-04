# Mono Urbano

Automatización de contenido para Instagram protagonizada por un macaco fotorrealista que vive una vida urbana común. El humor sale del contraste entre la normalidad de la escena y que el protagonista sea un mono.

```
[Ideación] → [Dedup vs historial] → [Prompt] → [Imagen] → [QC] → [Post-proceso]
   → [Caption] → [PR de aprobación] → [Instagram] → [Historial]
```

## Stack a costo $0
| Pieza | Herramienta | Costo |
|---|---|---|
| Cerebro (ideas, QC visual, captions) | `claude -p` (Claude Code) con token de suscripción Pro/Max | Incluido en el plan (crédito mensual del Agent SDK; dejar los créditos pagos desactivados) |
| Imagen automática | Cloudflare Workers AI, FLUX.2 con imágenes de referencia | Gratis: 10k neuronas por día |
| Imagen manual asistida | App de Gemini o AI Studio (gratis); Claude Design para piezas gráficas | Gratis |
| Video / reels | Slideshow con ffmpeg (Ken Burns) | Gratis |
| Hosting de medios | Cloudflare R2 | Gratis hasta 10 GB, sin egress |
| Orquestación | GitHub Actions (repo público) | Gratis |
| Publicación | Instagram API con Instagram Login | Gratis |

**Sobre Claude Design:** genera diseños y prototipos (HTML/SVG), no fotos fotorrealistas, y no tiene API de generación de imágenes. En este proyecto se usa como paso manual opcional para plantillas u overlays.

## Estado por fases
- [x] **Fase 1:** esqueleto, biblia, CLI con `--dry-run`, ideación + dedup.
- [ ] **Fase 2:** adapters de imagen (Cloudflare / manual / mock), QC y post-proceso.
- [ ] **Fase 3:** captions, cola y PR de aprobación.
- [ ] **Fase 4:** publicación en Instagram + R2.
- [ ] **Fase 5:** reels.
- [ ] **Fase 6:** Actions programadas, refresh de token, notificaciones y README final.

## Uso local
```bash
pip install -e ".[dev]"
cp .env.example .env              # completar lo que haga falta
mono generate -n 10 --dry-run     # 10 ideas distintas + prompts, sin red
mono generate -n 4 -f feed        # tanda real (requiere `claude` logueado)
mono generate -n 5 -f carousel --theme "un domingo en San Telmo"
mono generate -n 6 --scene tienda_camisetas
mono history --stats
pytest -q
```

## Estructura
- `character/`: `bible.yaml` (fuente de verdad), `bible.md`, `reference/` (identidad canónica) y `style_refs/` (solo estilo).
- `scenes/<lugar>/`: fotos reales de un ambiente + `scene.yaml`.
- `prompts/`: plantillas de ideación, prompt de imagen, QC y caption.
- `src/mono/`: el pipeline (ver `CLAUDE.md`).
- `data/`: `history.jsonl`, `idea_bank.yaml` y `queue.yaml`.
- `drafts/<tanda>/`: piezas de cada tanda (las revisás en el PR).

## Escenas de referencia
Creá `scenes/<nombre>/` con fotos del lugar y un `scene.yaml` opcional (`description`, `keep`, `action_ideas`). Después corré `mono generate --scene <nombre>`: todas las ideas ocurren en ese lugar, con acciones distintas.
