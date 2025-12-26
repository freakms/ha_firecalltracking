# Einsatz-Monitor - Home Assistant Integration

Diese HACS-Integration verbindet Ihren Home Assistant mit dem Einsatz-Monitor (FireCall Tracker).

## Features

- 🚨 **Echtzeit-Alarme** via WebSocket
- 📊 **Sensoren** für Einsatzdaten
- 🔔 **Events** für Automationen
- 🔐 **Sichere Token-Authentifizierung**
- 🎴 **Custom Lovelace Card** für Dashboard-Anzeige

## Installation

### Via HACS (empfohlen)

1. Öffnen Sie HACS in Home Assistant
2. Klicken Sie auf "Integrationen"
3. Klicken Sie auf die drei Punkte oben rechts → "Benutzerdefinierte Repositories"
4. Fügen Sie die Repository-URL hinzu
5. Wählen Sie "Integration" als Kategorie
6. Klicken Sie auf "Hinzufügen"
7. Suchen Sie nach "Einsatz-Monitor" und installieren Sie es
8. Starten Sie Home Assistant neu

### Manuelle Installation

1. Kopieren Sie den Ordner `custom_components/einsatz_monitor` in Ihr Home Assistant `config/custom_components/` Verzeichnis
2. Starten Sie Home Assistant neu

## Konfiguration

### 1. Token generieren

1. Melden Sie sich im Einsatz-Monitor an
2. Gehen Sie zu Einstellungen → Home Assistant
3. Klicken Sie auf "Token generieren"
4. Kopieren Sie den generierten Token

### 2. Integration hinzufügen

1. Gehen Sie in Home Assistant zu Einstellungen → Integrationen
2. Klicken Sie auf "Integration hinzufügen"
3. Suchen Sie nach "Einsatz-Monitor"
4. Geben Sie ein:
   - **Server URL**: Die URL Ihres Einsatz-Monitors (z.B. `https://tracker.meine-feuerwehr.de`)
   - **API Token**: Der generierte Token (beginnt mit `ha_`)

## Sensoren

| Sensor | Beschreibung |
|--------|-------------|
| `sensor.einsatze_24h` | Anzahl der Einsätze in den letzten 24 Stunden |
| `sensor.letzter_einsatz_stichwort` | Stichwort des letzten Einsatzes |
| `sensor.letzter_einsatz_fahrzeuge` | Fahrzeuge des letzten Einsatzes |
| `sensor.letzter_einsatz_zeit` | Zeitstempel des letzten Einsatzes |
| `sensor.letzte_einsatze` | **NEU:** Liste der letzten 5 Einsätze |
| `binary_sensor.einsatz_status` | Zeigt "Einsatz aktiv" oder "Kein Einsatz" |

## Custom Lovelace Card

Die Integration enthält eine Custom Card zur Anzeige der letzten 5 Einsätze mit farblicher Kennzeichnung:

- 🔴 **Rot mit Flamme** - Brand-Einsätze (B1, B2, Brand, etc.)
- 🔵 **Blau mit Auto** - Technische Hilfe / VU (TH, H1, VU, etc.)
- 🟠 **Orange** - Gefahrgut (ABC, GSG, etc.)

### Card einrichten

1. **Ressource hinzufügen** (falls nicht automatisch):
   
   Gehen Sie zu Einstellungen → Dashboards → Ressourcen → Ressource hinzufügen:
   ```
   URL: /local/einsatz_monitor/einsatz-monitor-card.js
   Typ: JavaScript-Modul
   ```

2. **Card zum Dashboard hinzufügen**:
   
   YAML-Modus:
   ```yaml
   type: custom:einsatz-monitor-card
   entity: sensor.letzte_einsatze
   title: Letzte Einsätze
   ```

   Oder über die UI:
   - Dashboard bearbeiten
   - Karte hinzufügen
   - Nach "Einsatz-Monitor Card" suchen

### Card Optionen

| Option | Beschreibung | Standard |
|--------|-------------|----------|
| `entity` | Entity ID des Einsatz-Listen-Sensors | `sensor.letzte_einsatze` |
| `title` | Titel der Karte | "Letzte Einsätze" |
| `show_header` | Header anzeigen | `true` |

## Events

Bei einem neuen Alarm wird das Event `einsatz_monitor_new_alarm` ausgelöst:

```yaml
automation:
  - alias: "Alarm Benachrichtigung"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    action:
      - service: notify.mobile_app_handy
        data:
          title: "🚨 ALARM"
          message: "{{ trigger.event.data.keyword }} - {{ trigger.event.data.vehicles }}"
```

## Beispiel-Automatisierungen

### Push-Benachrichtigung bei Alarm

```yaml
automation:
  - alias: "Feuerwehr Alarm - Benachrichtigung"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    action:
      - service: notify.mobile_app_ihr_handy
        data:
          title: "🚨 ALARM"
          message: "{{ trigger.event.data.keyword }} - {{ trigger.event.data.vehicles }}"
          data:
            priority: high
            ttl: 0
```

### Lichter rot bei Brand-Einsatz

```yaml
automation:
  - alias: "Brand-Alarm - Lichter rot"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    condition:
      - condition: template
        value_template: >
          {{ 'B' in trigger.event.data.keyword.upper() or 
             'BRAND' in trigger.event.data.keyword.upper() }}
    action:
      - service: light.turn_on
        target:
          entity_id: light.wohnzimmer
        data:
          color_name: red
          brightness: 255
```

### Sprachausgabe (TTS)

```yaml
automation:
  - alias: "Feuerwehr Alarm - Durchsage"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    action:
      - service: tts.speak
        target:
          entity_id: tts.google_translate
        data:
          media_player_entity_id: media_player.wohnzimmer
          message: >
            Achtung Alarm! {{ trigger.event.data.keyword }}. 
            Fahrzeuge: {{ trigger.event.data.vehicles }}
```

## Troubleshooting

### Verbindung fehlgeschlagen
- Prüfen Sie, ob die Server-URL korrekt ist
- Testen Sie die URL im Browser: `https://ihre-domain.de/api/health`

### Token ungültig
- Generieren Sie einen neuen Token im Einsatz-Monitor
- Tokens verfallen nicht automatisch, können aber vom Admin zurückgesetzt werden

### Keine Echtzeit-Updates
- Stellen Sie sicher, dass "WebSocket nutzen" aktiviert ist
- Manche Firewalls blockieren WebSocket-Verbindungen
- Fallback: Polling funktioniert immer (Abfrageintervall reduzieren)

### Card wird nicht angezeigt
- Prüfen Sie, ob die Ressource korrekt hinzugefügt wurde
- Leeren Sie den Browser-Cache
- Starten Sie Home Assistant neu

## Support

Bei Problemen erstellen Sie ein Issue im GitHub Repository.
