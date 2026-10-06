# CLAUDE.md: reglas para futuras sesiones

## Proyecto
Este repo automatiza contenido de Instagram con un **macaco fotorrealista** que vive una vida urbana común. El código está en `src/mono/` (Python 3.11) y la CLI es `mono`. Objetivo de costo: **$0**.

## Reglas del personaje (no negociables)
- La fuente de verdad es `character/bible.yaml`; `bible.md` explica el criterio. Todo prompt de imagen se arma desde la biblia en `src/mono/prompting/builder.py`.
- Siempre es el **mismo macaco** de `character/reference/`. Nunca chimpancé, gorila, caricatura ni render 3D.
- `character/style_refs/` sirve solo para encuadre y estilo; **nunca** se usa como referencia de identidad.
- Pide N imágenes → entrega N archivos independientes. Nunca collage ni grilla.
- Es un macaco **adulto**, como las referencias. Estética de foto real, limpia y nítida con luz natural (como `character/reference/`). Nada de grano fuerte, flash, blanco y negro, HDR, look publicitario ni look "IA".

## Arquitectura
`ideation → dedup → prompting → providers → qc → postprocess → captions → PR → publish → history`
- **LLM:** `llm/` con los adapters `claude_cli` (default, `claude -p` con la suscripción), `anthropic_api` y `mock`.
- **Imagen:** `providers/` con adapters intercambiables. El resto del pipeline no depende del proveedor.
- **Estado en archivos:** `data/history.jsonl`, `data/queue.yaml` y `data/idea_bank.yaml`.
- **Variedad:** `ideation/dedup.py` combina TF-IDF con reglas por ejes y compara contra el historial y contra la tanda.

## Flujo
- **Generación:** `generate.yml` abre un PR por corrida.
- **Aprobación:** mergear el PR aprueba la tanda. Borrar un `.jpg` en el PR descarta esa pieza.
- **Cola:** `approve.yml` corre `mono approve`, que agenda las piezas en `data/queue.yaml`.
- **Modo manual:** subís `inbox/<id>.jpg` a la rama del PR y `ingest.yml` lo procesa.
- **Publicación:** `publish.yml` corre a las 13:07 y 19:07 de Buenos Aires y llama a `mono publish`, que publica lo vencido.
- **Token:** `token-refresh.yml` lo renueva los lunes; necesita el secret `GH_PAT`.
- **Avisos:** `src/mono/notify.py` maneja los canales `github_issue` (deduplica por título y usa el label `alerta`), `email` y `telegram`. Un aviso nunca rompe el flujo.
- **Salud y limpieza:** `mono doctor` muestra qué falta configurar y `mono prune` libera los medios de tandas viejas ya publicadas.
- **Estados de una pieza:** `draft`, `awaiting_manual`, `qc_failed`, `approved`, `queued`, `published` y `discarded`.

## Convenciones
- Todo comando soporta `--dry-run`, que usa el LLM mock, no hace llamadas de red y no escribe en `data/`.
- Nunca se commitean secretos. Viven en `.env` (local) o en GitHub Secrets, y la plantilla es `.env.example`.
- Los tests aíslan las credenciales del entorno (`tests/conftest.py`): nunca deben mandar avisos ni llamar APIs reales.
- Antes de pushear corré `pytest -q` y `ruff check src tests`.
- Commits chicos y descriptivos.
