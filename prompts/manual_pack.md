# Paquete manual: $item_id

1. Abrí la app de Gemini (gemini.google.com) o Google AI Studio. Ambas son gratis y generan imágenes con referencias.
2. Adjuntá estas imágenes del personaje (identidad):
$references
3. Si hay una foto del lugar, adjuntala también:
$scene
4. Pegá el prompt de abajo. Formato vertical $ratio. Generá **una sola imagen**: nunca collage ni grilla.
5. Guardá el resultado como `inbox/$item_id.jpg` (o .png) en la rama del PR de la tanda y corré `mono ingest` (o esperá al workflow).

```text
The attached photos show the character: always this same real macaque, same face, fur and proportions. Ignore their clothes and backgrounds. If a location photo is attached, use it as the exact setting.

$prompt
```
