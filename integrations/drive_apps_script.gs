/**
 * Mono Urbano → Google Drive (gratis, corre con tu cuenta de Google).
 *
 * Recibe archivos desde GitHub Actions y los guarda en la carpeta "Monkey" de tu Drive.
 * Instalación (una sola vez):
 *   1. Entrá a https://script.google.com → "Nuevo proyecto".
 *   2. Borrá todo y pegá este archivo completo.
 *   3. Cambiá SECRET por una clave inventada (letras y números, 20+ caracteres).
 *   4. Implementar → Nueva implementación → tipo "Aplicación web".
 *      Ejecutar como: "Yo"   ·   Quién tiene acceso: "Cualquier usuario".
 *   5. Autorizá los permisos y copiá la URL que termina en /exec.
 *   6. En GitHub (Settings → Secrets → Actions) cargá:
 *        DRIVE_WEBHOOK_URL    = esa URL
 *        DRIVE_WEBHOOK_SECRET = la misma clave que pusiste en SECRET
 */
const SECRET = 'CAMBIAR-POR-UNA-CLAVE-LARGA';
const ROOT_FOLDER = 'Monkey';

function doGet() {
  return json_({ ok: true, folder: ROOT_FOLDER });
}

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.secret !== SECRET) return json_({ ok: false, error: 'secret inválido' });
    const folder = ensurePath_(req.path || '');
    const bytes = Utilities.base64Decode(req.base64);
    const blob = Utilities.newBlob(bytes, req.mimeType || 'application/octet-stream', req.filename);
    const old = folder.getFilesByName(req.filename);
    while (old.hasNext()) old.next().setTrashed(true);   // reemplaza si ya existía
    const file = folder.createFile(blob);
    return json_({ ok: true, id: file.getId(), url: file.getUrl() });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function ensurePath_(path) {
  const roots = DriveApp.getRootFolder().getFoldersByName(ROOT_FOLDER);
  let folder = roots.hasNext() ? roots.next() : DriveApp.getRootFolder().createFolder(ROOT_FOLDER);
  path.split('/').filter(String).forEach(function (name) {
    const it = folder.getFoldersByName(name);
    folder = it.hasNext() ? it.next() : folder.createFolder(name);
  });
  return folder;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
