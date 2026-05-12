# Einsatz-Monitor für Home Assistant

Custom Integration für den FireCall Tracker — verbindet Home Assistant mit dem Einsatz-Monitor für Echtzeit-Alarmbenachrichtigungen via WebSocket oder Polling.

by freakms - ich schwöre feierlich ich bin ein tunichtgut

---

## Funktionen

- **Sensoren**: Einsatzzähler, letztes Stichwort, Fahrzeuge, Zeitstempel, Liste der letzten 5 Einsätze
- **Echtzeit-Updates**: Via WebSocket (bevorzugt) mit automatischem Fallback auf Polling
- **Sprachausgabe**: Alexa, Sonos, Google Home/Nest oder generisches TTS
- **Licht-Alarm**: Automatisches Einschalten mit Farbe und Timer, Zustand wird wiederhergestellt
- **Dashboard-Card**: Letzte 5 Einsätze farblich nach Brand / TH / Gefahrgut unterschieden
- **HA-Events**: `einsatz_monitor_new_alarm` für eigene Automationen

---

## Voraussetzungen

### Für alle Speaker-Typen
- Home Assistant 2023.1 oder neuer

### Für Alexa (Amazon Echo)
> ⚠️ **Pflicht: HACS-Integration installieren**
>
> Alexa-Sprachausgabe benötigt die Community-Integration **alexa_media_player**.
> Diese ist **nicht** standardmäßig in Home Assistant enthalten.
>
> **Installation:**
> 1. [HACS](https://hacs.xyz) in Home Assistant öffnen
> 2. Integrationen → Suche nach **"Alexa Media Player"**
> 3. Installieren und Home Assistant neu starten
> 4. Einstellungen → Geräte & Dienste → Alexa Media Player hinzufügen → Amazon-Login
>
> Danach erscheinen die Echo-Geräte als `media_player.*` in Home Assistant.

### Für Sonos
Sonos-Lautsprecher werden automatisch von der eingebauten Sonos-Integration erkannt. Keine Zusatzinstallation nötig. Die Sprachausgabe läuft über `tts.google_translate_say` auf dem Sonos-Gerät.

### Für Google Home / Nest
Google-Geräte werden über die eingebaute Google Cast-Integration erkannt (Einstellungen → Geräte & Dienste → Google Cast). Die Ansage läuft über `tts.google_translate_say`.

### Für andere Lautsprecher (generisches TTS)
Jedes Gerät das in HA als `media_player` erscheint kann mit dem Typ **"Generisches TTS"** genutzt werden. Die Ansage läuft über `tts.speak` — kompatibel mit fast allen Speakern die TTS unterstützen.

---

## Installation via HACS

1. HACS öffnen
2. Integrationen → Drei-Punkte-Menü → **"Benutzerdefinierte Repositories"**
3. URL eingeben: `https://github.com/freakms/ha_firecalltracking`
4. Kategorie: **Integration**
5. **"Einsatz-Monitor"** suchen und installieren
6. Home Assistant neu starten

---

## Einrichtung

1. Einstellungen → Geräte & Dienste → **Integration hinzufügen**
2. Nach **"Einsatz-Monitor"** suchen
3. Server-URL und Token eingeben

**Token generieren:**
- FireCall Tracker → Einstellungen → Home Assistant → Token generieren
- Der Token beginnt mit `ha_`

---

## Optionen konfigurieren

Nach der Einrichtung: Integration → **"Konfigurieren"**

### Sprachausgabe

| Lautsprecher-Typ | Beschreibung | Voraussetzung |
|---|---|---|
| `alexa` | Amazon Echo-Geräte | HACS alexa_media_player |
| `sonos` | Sonos-Lautsprecher | Eingebaute Sonos-Integration |
| `google` | Google Home / Nest | Eingebaute Google Cast-Integration |
| `generic_tts` | Alle anderen Speaker | Keiner (tts.speak) |

**Nachrichtenvorlage** — verfügbare Platzhalter:
```
{keyword}    → Einsatzstichwort (z.B. "B2 - Wohnungsbrand")
{unit}       → Alarmierte Einheit (z.B. "10-Lüneburg Mitte")
{vehicles}   → Fahrzeuge (z.B. "LF 10, DLK 23")
{timestamp}  → Zeitstempel
```

Beispiel: `Achtung Feuerwehreinsatz! Stichwort {keyword}. Fahrzeuge: {vehicles}`

### Licht-Alarm

- Mehrere Lampen gleichzeitig auswählbar
- Farben: Rot, Blau, Orange, Weiß
- Dauer: 0 = nicht automatisch ausschalten
- Vorheriger Zustand (Farbe, Helligkeit) wird nach Ablauf wiederhergestellt

---

## Dashboard-Card

Die Card wird automatisch als Lovelace-Ressource registriert.

**YAML-Konfiguration:**
```yaml
type: custom:einsatz-monitor-card
entity: sensor.letzte_einsatze
title: Letzte Einsätze
```

**Farbkodierung:**
- 🔴 Rot — Brand (B1-B5, GMA, BMA, FEUER)
- 🔵 Blau — Technische Hilfe (TH, VU, H1-H5, THL, PERSON)
- 🟡 Gelb — Gefahrgut (ABC, GSG, GAS, ÖL, CHEMIE)
- ⚫ Grau — Sonstige

---

## Eigene Automationen

Die Integration feuert bei jedem neuen Einsatz das Event `einsatz_monitor_new_alarm`:

```yaml
automation:
  - alias: "Einsatz Push-Benachrichtigung"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    action:
      - service: notify.mobile_app_mein_handy
        data:
          title: "🚒 Alarm!"
          message: "{{ trigger.event.data.keyword }} — {{ trigger.event.data.vehicles }}"

  - alias: "Einsatz Licht rot"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    condition:
      - condition: template
        value_template: "{{ 'B' in trigger.event.data.keyword }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.wohnzimmer
        data:
          rgb_color: [255, 0, 0]
```

---

## Fehlerbehebung

**Sensor zeigt "Entity nicht gefunden":**
Prüfen ob der Sensor-Name stimmt: Einstellungen → Geräte & Dienste → Einsatz-Monitor → Entitäten

**Alexa spricht nicht:**
1. Ist `alexa_media_player` via HACS installiert und eingerichtet?
2. Erscheint das Echo-Gerät unter Einstellungen → Geräte als `media_player.*`?
3. Ist der richtige Speaker-Typ (`alexa`) ausgewählt?

**WebSocket-Fehler im Log:**
WebSocket benötigt korrekte Proxy-Konfiguration (nginx `Upgrade`-Header). Polling funktioniert als Fallback automatisch.

**Doppelte Sprachausgabe:**
Ab v1.4.0 behoben — WebSocket und Polling teilen eine gemeinsame Liste verarbeiteter Alarm-IDs.
