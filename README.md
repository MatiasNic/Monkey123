# Mono Urbano

Automatización de contenido para Instagram protagonizada por un **macaco fotorrealista** que vive una vida urbana común. El humor sale del contraste entre la normalidad de la escena y que el protagonista sea un mono.

```
[Ideación] → [Dedup vs historial] → [Prompt] → [Imagen] → [QC] → [Post-proceso]
   → [Caption] → [PR de aprobación] → [Cola] → [Instagram] → [Historial] → [Avisos]
```

## Stack a costo $0
| Pieza | Herramienta | Costo |
|---|---|---|
| Cerebro (ideas, QC visual, captions) | `claude -p` (Claude Code) con token de suscripción Pro/Max | Incluido en el plan (crédito mensual del Agent SDK; dejar los créditos pagos **desactivados**) |
| Imagen automática | Cloudflare Workers AI: FLUX.2 con imágenes de referencia | Gratis: 10k neuronas por día |
| Imagen manual asistida | App de Gemini o AI Studio (gratis) | Gratis |
| Reels | Slideshow Ken Burns con ffmpeg | Gratis |
| Hosting de medios | Cloudflare R2 | Gratis hasta 10 GB, sin egress |
| Orquestación | GitHub Actions (repo público) | Gratis |
| Publicación | Instagram API con Instagram Login | Gratis |
| Avisos | GitHub Issues, email por SMTP o bot de Telegram | Gratis |

**Sobre Claude Design:** genera diseños y prototipos (HTML/SVG), no fotos fotorrealistas, y no tiene API de generación de imágenes. En este proyecto queda como paso manual opcional para plantillas u overlays.

---

## Puesta en marcha (checklist)
Seguí los pasos en orden. Corré `mono doctor` (local) o el workflow **doctor** (Actions) para ver qué falta.

1. **Rama `main`:** mergeá el PR inicial a `main` y en *Settings → General → Default branch* elegí `main`. Los crons de GitHub **solo corren desde la rama por defecto**.
2. **Permisos de Actions:** en *Settings → Actions → General → Workflow permissions*, elegí **Read and write** y tildá **Allow GitHub Actions to create and approve pull requests**.
3. **Secrets** (*Settings → Secrets and variables → Actions*):

   | Secret | Para qué | Dónde se obtiene |
   |---|---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | Ideas, QC y captions | `claude setup-token` en tu compu (suscripción Pro/Max) |
   | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Generar imágenes | dash.cloudflare.com → *Workers AI* → API token con permiso Workers AI |
   | `IG_USER_ID`, `IG_ACCESS_TOKEN` | Publicar | Ver [Setup de Meta](#setup-de-meta) |
   | `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Hosting temporal de medios | Ver [Setup de R2](#setup-de-cloudflare-r2) |
   | `GH_PAT` | Renovar solo el token de Instagram | GitHub → *Settings → Developer settings → Fine-grained tokens*, solo este repo, permiso **Secrets: Read and write** |
   | `SMTP_*`, `NOTIFY_EMAIL_TO` *(opcional)* | Avisos por email | Por ejemplo Gmail con [contraseña de aplicación](https://myaccount.google.com/apppasswords); `SMTP_HOST=smtp.gmail.com` |
   | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` *(opcional)* | Avisos por Telegram | @BotFather + el id de tu chat |
4. **Costo $0 en Claude:** en claude.ai, activá el crédito mensual del Agent SDK y dejá desactivados los créditos pagos.
5. **Chequeo:** corré *Actions → doctor → Run workflow*. Todo lo obligatorio tiene que quedar en ✅.
6. **Primer post de prueba:** corré `mono publish-test character/reference/ref_02_balcon_diario_b.jpg --caption "prueba."` en local, o la primera tanda con *Actions → generate*.
7. **Canales de aviso:** elegilos en `config.yaml → notifications`.

---

## Google Drive (carpeta Monkey)
Todo lo que se genera se copia automáticamente a la carpeta **Monkey** de tu Google Drive:
```
Monkey/
  AAAA-MM-DD/              una carpeta por día (juntás todas las tandas de ese día)
    feed/  story/  carrusel/  reel/   fotos finales (y el video del reel) por formato
    descartadas/           intentos que el control de calidad rechazó
    manual/                paquetes para generar a mano (si usaste el modo manual)
    resumen_<tanda>.md     ideas, captions, hashtags y notas de calidad de cada tanda
  publicadas/AAAA-MM-DD/   copia de cada post publicado + .txt con caption y link de Instagram
```
Es gratis y no necesita Google Cloud: un pequeño script corre con tu cuenta y recibe los archivos.

**Instalación (una sola vez, unos 5 minutos):**
1. Entrá a https://script.google.com y tocá **Nuevo proyecto**.
2. Borrá todo el código que aparece y pegá el contenido de [`integrations/drive_apps_script.gs`](integrations/drive_apps_script.gs).
3. En la línea `const SECRET = '...'`, reemplazá el texto por una clave inventada, de 20 o más letras y números.
4. Guardá (💾). Después tocá **Implementar → Nueva implementación**, en el engranaje elegí **Aplicación web** y configurá:
   - Ejecutar como: **Yo**.
   - Quién tiene acceso: **Cualquier usuario**.
   
   Tocá **Implementar**.
5. Google te pide autorizar. Si aparece *"Google no verificó esta app"*, tocá **Configuración avanzada → Ir a … (no seguro)**: la app es tuya.
6. Copiá la **URL de la aplicación web**, la que termina en `/exec`.
7. En GitHub, en *Settings → Secrets → Actions*, cargá `DRIVE_WEBHOOK_URL` con esa URL y `DRIVE_WEBHOOK_SECRET` con la misma clave del paso 3.

Si esos secrets no están cargados, el sistema sigue funcionando igual y simplemente no copia nada a Drive. Para subir a mano: `mono drive-sync` (o `--batch <id>`, o `--dry-run` para ver qué subiría).

## Operación semanal
| Cuándo (Buenos Aires) | Workflow | Qué pasa |
|---|---|---|
| Dom y mié 09:00 | `generate` | Genera las tandas de `config.yaml → generate_plan` y abre **un PR** con fotos, captions, QC y el video del reel. Te avisa `batch_ready` si lo activás. |
| Cuando revisás | — | Para descartar una pieza, **borrá su .jpg** en el PR. **Mergear = aprobar.** |
| Al mergear | `approve` | Agenda las piezas aprobadas en `data/queue.yaml` según `schedule.slots` (feed lun/mié/vie 19:00, carrusel sábado, historias mar/jue/sáb/dom 13:00, reel domingo). |
| Todos los días 13:07 y 19:07 | `publish` | Publica lo vencido: R2 → contenedores → publish → historial → limpieza de R2. Si no hay nada vencido, termina sin usar credenciales. |
| Lunes 10:17 | `token-refresh` | Renueva el token de Instagram (60 días), actualiza el secret y registra el vencimiento en `data/token_status.yaml`. |
| En cada push | `ci` | Corre ruff, pytest y una tanda en dry-run. |
| Manual | `ingest` | Modo manual: subís `inbox/<id>.jpg` a la rama del PR y lo procesa (también se dispara solo con el push). |
| Manual | `doctor` | Chequeo de salud con los secrets reales. |

**Si algo falla:** se avisa por los canales configurados. Con GitHub Issues, una falla repetida **comenta en el mismo issue** (label `alerta`) en vez de abrir uno nuevo, y GitHub te manda el aviso por mail.

---

## Comandos
```bash
pip install -e ".[dev,publish]"
cp .env.example .env                      # credenciales locales (nunca se commitea)

# Generar
mono generate -n 10 --dry-run             # tanda completa con mocks, sin red
mono generate -n 4 --ideas-only           # solo ideas + prompts
mono generate -n 4 -f feed                # real, con Cloudflare
mono generate -n 5 -f carousel --theme "un domingo en San Telmo"
mono generate -n 4 -f reel
mono generate -n 6 --scene tienda_camisetas
mono generate -n 3 --provider manual      # paquetes para la app de Gemini
mono ingest                               # procesa inbox/<id>.jpg

# Revisar, aprobar y agendar
mono review <tanda> | mono approve | mono queue [--due] | mono plan

# Publicar
mono publish [--dry-run] [--id post-…]
mono publish-test foto.jpg --caption "…" [--story] [--dry-run]

# Mantenimiento
mono doctor [--online]                    # qué falta configurar + estado
mono refresh-token | mono token-check
mono notify --event failure --title "…" --body "…" [--dry-run]
mono history [--stats]
mono prune --days 60 [--dry-run]          # borra JPG/MP4 de tandas ya publicadas
```

---

## Cómo funciona

### Personaje y variedad
- **Biblia:** `character/bible.yaml` es la fuente de verdad (identidad, ejes de variedad y 9 looks de cámara con sus parámetros de retoque). `bible.md` explica el criterio.
- **Referencias:** las de identidad están en `character/reference/`. `character/style_refs/` sirve **solo** para estilo.
- **Variedad:** Claude propone ideas que varían a la vez lugar, actividad, pose, encuadre, ropa, luz y look. Un filtro local (TF-IDF + reglas por eje) descarta las que se parecen demasiado al historial o a otras de la misma tanda. Las ideas se toman de `data/idea_bank.yaml` y el banco se va ampliando.
- **Escenas de referencia:** creá `scenes/<lugar>/` con fotos del lugar y un `scene.yaml` (`description`, `keep`, `action_ideas`), y usá `--scene <lugar>`.

### Imagen, QC y retoque
| Proveedor | Cuándo | Cómo |
|---|---|---|
| `cloudflare` (default) | Automático | FLUX.2 con hasta 4 imágenes de entrada (escena + referencias del mono). Por defecto usa `flux-2-klein-4b` (unas 50 imágenes por día gratis). `flux-2-klein-9b` mantiene mejor el parecido, pero alcanza solo para 5 o 6 por día. Se elige en `config.yaml → image.cloudflare_model`. |
| `manual` | Mejor consistencia, también gratis | `drafts/<tanda>/manual/<id>.md` trae el prompt y las referencias. Generás en Gemini, subís `inbox/<id>.jpg` y corrés `mono ingest`. |
| `mock` | Tests y `--dry-run` | Imagen sintética, sin red. |

**QC:**
1. Primero corren heurísticas locales: detectan collages, grillas y dípticos, imágenes vacías y resolución baja.
1b. Claude cuenta brazos, manos, piernas y pies. Si encuentra uno de más o duplicado (por ejemplo, 3 pies), o la anatomía saca menos de `qc.min_anatomy`, la imagen se rechaza directo, aunque el resto esté perfecto.
2. Después Claude, con visión, compara la imagen contra las referencias. Cuenta como falla dura si no es un macaco, si es un collage o si tiene texto superpuesto.
3. Si no pasa, se regenera hasta 3 veces.

**Retoque:** los looks son limpios, como las fotos de referencia: el post-proceso es mínimo (un grano casi invisible y un leve ajuste de color para sacar el brillo "IA"). Después recorta a 1080×1350 o 1080×1920 y guarda un JPEG sRGB sin EXIF, de hasta 8 MB.

### Captions
En español rioplatense, con voz canchera y seca y sin explicar el chiste, más alt text y entre 2 y 5 hashtags. Claude ve los captions recientes para no repetirse. Un carrusel o un reel lleva un solo caption; las historias no llevan.

### Reels
De 2 a 10 fotos verticales de una misma salida, cada una con un movimiento distinto (zoom o paneo) y un fundido de 0,4 s, a 2,5 s por foto. El video sale en MP4 H.264 1080×1920 a 30 fps, con audio AAC 48 kHz y `faststart`.
- **Audio:** si hay pistas libres de derechos en `audio/`, cada reel usa una. Si no, sale con audio silencioso.
- **Revisión:** si borrás fotos en el PR, el video se rearma solo con las aprobadas.
- **A futuro:** `video.provider` es un adapter intercambiable para sumar un proveedor de video IA cuando haya opción gratis o presupuesto.

### Publicación y etiqueta de IA
Usa la Instagram API con Instagram Login (`graph.instagram.com`), que **no** requiere página de Facebook. Soporta IMAGE, STORIES, CAROUSEL y REELS.
- **Etiqueta de IA:** todo sale con `is_ai_generated=true`, que activa la etiqueta "Información de IA" de Meta. En los carruseles va en el post padre, porque la API no la acepta en los hijos. Si además querés un texto visible, completá `captions.ai_disclosure_text`.
- **Si algo falla:** la entrada sigue en la cola y se reintenta; al tercer fallo pasa a `failed` y se avisa.
- **Límite:** antes de publicar se chequea el máximo de 100 publicaciones por API cada 24 h.

### Setup de Meta
1. **Cuenta profesional:** en la app de Instagram, Configuración → *Tipo de cuenta y herramientas* → *Cambiar a cuenta profesional* → **Creator** o **Business**.
2. **App de Meta:** en [developers.facebook.com](https://developers.facebook.com) → *My Apps* → *Create app*. Caso de uso: Instagram API ("Administrar mensajes y contenido en Instagram"). Tipo: **Business**.
3. En **Instagram → API setup with Instagram login** → *Generate access tokens* → **Add account**, entrá con la cuenta del mono y aceptá `instagram_business_basic` + `instagram_business_content_publish`.
4. Copiá el **token** y el **Instagram user ID** en los Secrets `IG_ACCESS_TOKEN` e `IG_USER_ID`. En modo desarrollo alcanza para tu propia cuenta, sin App Review.
5. El token dura 60 días. `token-refresh` lo renueva cada semana si cargaste `GH_PAT`. Si no, te avisa antes de que venza.

### Setup de Cloudflare R2
1. Dashboard → **R2** → *Create bucket*. Cloudflare puede pedir una tarjeta para activar R2, aunque el uso quede dentro del tier gratis.
2. En el bucket → *Settings* → **Public Development URL** → *Enable*. Eso da `https://pub-xxxx.r2.dev`, que va en `R2_PUBLIC_BASE_URL`.
3. **R2 → Manage API tokens** → *Create API token* con permiso **Object Read & Write** sobre ese bucket. Te da `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`. `R2_ACCOUNT_ID` es el Account ID de Cloudflare.

---

## Costos y límites
- **Cloudflare Workers AI:** 10.000 neuronas por día gratis, que se reinician a las 00:00 UTC (21:00 en Buenos Aires).
  - Con `flux-2-klein-4b` (default), cada foto de 1024×1280 gasta unas 180 neuronas: alcanzan para unas 50 por día, contando reintentos. Con `flux-2-klein-9b` gasta unas 1.700 y alcanzan para 5 o 6.
  - Si la cuota se agota en medio de una tanda, el sistema deja de pedir fotos y las que faltan quedan marcadas "cuota agotada". Si no salió ninguna, `generate` falla con ese mensaje y no abre un PR vacío.
- **Claude (`claude -p`):** usa el crédito mensual del Agent SDK de tu plan (USD 20 en Pro). Cada tanda gasta ideación + 1 QC por imagen (con reintentos) + captions. Si se agota, se frena hasta el próximo ciclo; con los créditos pagos desactivados, nunca se cobra.
- **Instagram:** 100 posts por API cada 24 h. El token dura 60 días.
- **R2:** 10 GB gratis. Los medios se borran después de publicar.
- **Repo:** cada foto pesa unos 0,6 MB y cada reel unos 5 MB. `mono prune` libera espacio de tandas publicadas hace más de 60 días; el historial y los permalinks se conservan.

## Troubleshooting
| Síntoma | Causa y solución |
|---|---|
| Los crons no corren | La rama por defecto no es `main`, o el repo tuvo 60 días sin actividad (GitHub pausa los crons; reactivalos desde Actions). |
| `generate` no abre el PR | Falta el permiso "Allow GitHub Actions to create and approve pull requests". |
| Muchas piezas `discarded` por QC | Bajá `qc.pass_score` (default 7), probá `flux-2-klein-9b` (mejor parecido, menos fotos por día) o usá el modo `manual`. Mirá los motivos en `batch.md` y en `output/rejected/`. |
| "Cuota de Cloudflare agotada" | Se gastaron las 10.000 neuronas del día. Volvé a correr `generate` después de las 21:00 (Buenos Aires) o usá el modo `manual`. |
| `publish` falla con error de token | El token venció. Generá uno nuevo en Meta, actualizá `IG_ACCESS_TOKEN` y cargá `GH_PAT` para que se renueve solo. |
| `publish` falla con un error de `image_url` | R2 no es público. Activá la Public Development URL y revisá `R2_PUBLIC_BASE_URL`. |
| `claude -p` falla en Actions | `CLAUDE_CODE_OAUTH_TOKEN` vencido o crédito agotado. Volvé a correr `claude setup-token`. |

## Estructura
- `character/`: biblia y referencias.
- `scenes/`: lugares de referencia.
- `prompts/`: plantillas para Claude.
- `audio/`: pistas para reels.
- `src/mono/`: el pipeline (ver `CLAUDE.md`).
- `data/`: historial, banco de ideas, cola y vencimiento del token.
- `drafts/<tanda>/`: piezas y `batch.md` de cada tanda.
- `inbox/`: imágenes manuales.
- `.github/workflows/`: automatización.
