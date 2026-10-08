#!/usr/bin/env python3
"""Notifica en Telegram los cambios recientes de Jira.

Eventos notificados:
  - Issues nuevos (creados en la ventana de consulta).
  - Cambios de estado (del historial de la issue).
  - Cambios de responsable (asignación).
  - Comentarios nuevos.

El estado (eventos ya notificados) se guarda en STATE_FILE para no repetir
mensajes entre ejecuciones. En la primera corrida se registran los eventos
existentes como línea base sin notificar, para evitar inundar el chat.
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JIRA_URL = os.environ.get("JIRA_URL", "https://grupo-2-ecci.atlassian.net").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = os.environ.get("STATE_FILE", ".jira-notif-state.json")

LOOKBACK_MIN = int(os.environ.get("LOOKBACK_MIN", "30"))
MAX_ISSUES = int(os.environ.get("MAX_ISSUES", "100"))
MAX_MENSAJES = int(os.environ.get("MAX_MENSAJES", "40"))
MAX_IDS_GUARDADOS = 1000
COMENTARIOS_MAX = 10
CAMPOS_EVENTO = {"Status", "Assignee"}


def fmt_jql_date(dt):
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}+0000"


def parse_fecha(s):
    s = s.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {s}")


def jira_get(path, params=None, timeout=30):
    url = f"{JIRA_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    cred = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {cred}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def enviar_telegram(texto):
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram rechazo el mensaje: {data}")
    time.sleep(0.4)


def texto_adf(nodo):
    if nodo is None:
        return ""
    if isinstance(nodo, str):
        return nodo
    if isinstance(nodo, list):
        return "".join(texto_adf(x) for x in nodo)
    if isinstance(nodo, dict):
        if nodo.get("type") == "text":
            return nodo.get("text", "")
        return "".join(texto_adf(h) for h in nodo.get("content", []))
    return ""


def cargar_estado():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            datos = json.load(fh)
        return set(datos.get("eventos", []))
    except (OSError, KeyError, ValueError):
        return None


def guardar_estado(eventos):
    ids = sorted(eventos)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump({"eventos": ids[-MAX_IDS_GUARDADOS:]}, fh)


def obtener_issues(ventana):
    jql = f"updated >= \"{fmt_jql_date(ventana)}\" ORDER BY updated DESC"
    issues = []
    token = None
    while len(issues) < MAX_ISSUES:
        params = {
            "jql": jql,
            "fields": "summary,status,assignee,issuetype,reporter,created,updated",
            "maxResults": min(50, MAX_ISSUES - len(issues)),
        }
        if token:
            params["nextPageToken"] = token
        pagina = jira_get("/rest/api/3/search/jql", params)
        issues.extend(pagina.get("issues", []))
        token = pagina.get("nextPageToken")
        if not token or not pagina.get("issues"):
            break
    return issues[:MAX_ISSUES]


def eventos_de_issue(issue, ventana, ya_vistos):
    key = issue["key"]
    campos = issue.get("fields", {})
    titulo = (campos.get("summary") or "").strip().replace("\n", " ")
    url = f"{JIRA_URL}/browse/{key}"
    eventos = []

    creado = parse_fecha(campos.get("created") or fmt_jql_date(ventana))
    if creado >= ventana:
        eventos.append((
            creado,
            f"created:{key}",
            "Nuevo issue {0}: {1}\n{2}\n{3}".format(
                (campos.get("issuetype") or {}).get("name", "Issue"),
                titulo,
                (campos.get("reporter") or {}).get("displayName", "sin reportero"),
                url,
            ),
        ))

    try:
        cambio = jira_get(f"/rest/api/3/issue/{key}/changelog",
                          {"maxResults": 100, "startAt": 0})
        total = cambio.get("total", 0)
        if total > 100:
            cambio = jira_get(f"/rest/api/3/issue/{key}/changelog",
                              {"maxResults": 100, "startAt": total - 100})
        for historia in cambio.get("histories", []):
            cuando = parse_fecha(historia["created"])
            if cuando < ventana:
                continue
            autor = (historia.get("author") or {}).get("displayName", "?")
            for item in historia.get("items", []):
                campo = item.get("field")
                if campo not in CAMPOS_EVENTO:
                    continue
                eid = f"history:{historia['id']}:{campo}"
                if eid in ya_vistos:
                    continue
                if campo == "Status":
                    texto = "Cambio de estado: '{0}' -> '{1}'\n{2} ({3})\n{4}".format(
                        item.get("fromString") or "sin estado",
                        item.get("toString") or "sin estado",
                        key, autor, url,
                    )
                else:
                    texto = "Asignacion: {0}\n{1} ({2})\n{3}".format(
                        item.get("toString") or "sin responsable",
                        key, autor, url,
                    )
                eventos.append((cuando, eid, texto))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"::warning::No se pudo leer el changelog de {key}: {exc}")

    try:
        comentarios = jira_get(
            f"/rest/api/3/issue/{key}/comment",
            {"orderBy": "-created", "maxResults": COMENTARIOS_MAX},
        )
        for com in reversed(comentarios.get("comments", [])):
            cuando = parse_fecha(com["created"])
            if cuando < ventana:
                continue
            eid = f"comment:{com['id']}"
            if eid in ya_vistos:
                continue
            cuerpo = " ".join(texto_adf(com.get("body")).split())
            if len(cuerpo) > 200:
                cuerpo = cuerpo[:200] + "..."
            autor = (com.get("author") or {}).get("displayName", "?")
            eventos.append((
                cuando,
                eid,
                "Comentario de {0} en {1}: {2}\n{3}".format(autor, key, cuerpo, url),
            ))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"::warning::No se pudieron leer los comentarios de {key}: {exc}")

    return eventos


def main():
    faltan = [nombre for nombre, valor in (
        ("JIRA_EMAIL", JIRA_EMAIL),
        ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
    ) if not valor]
    if faltan:
        print(f"::error::Faltan secrets en el workflow: {', '.join(faltan)}")
        sys.exit(1)

    ahora = datetime.now(timezone.utc)
    ventana = ahora - timedelta(minutes=LOOKBACK_MIN)

    ya_vistos = cargar_estado()
    primera_corrida = ya_vistos is None
    if primera_corrida:
        ya_vistos = set()
        print("Primera corrida: se registran los eventos existentes como linea base.")

    issues = obtener_issues(ventana)
    eventos = []
    for issue in issues:
        try:
            eventos.extend(eventos_de_issue(issue, ventana, ya_vistos))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            print(f"::warning::Error procesando {issue.get('key')}: {exc}")

    eventos.sort(key=lambda e: e[0])
    recortados = eventos[:MAX_MENSAJES]
    if len(eventos) > MAX_MENSAJES:
        print(f"::warning::{len(eventos)} eventos; se envian solo los primeros {MAX_MENSAJES}.")

    print(f"Issues en ventana: {len(issues)} | Eventos nuevos: {len(eventos)}")

    if primera_corrida:
        ya_vistos.update(eid for _, eid, _ in eventos)
    else:
        for _, _, texto in recortados:
            enviar_telegram(texto)
        ya_vistos.update(eid for _, eid, _ in recortados)

    guardar_estado(ya_vistos)
    print("Listo.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"::error::Fallo la notificacion: {exc}")
        sys.exit(1)
