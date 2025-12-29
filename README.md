# Einsatz-Monitor für Home Assistant

Diese Custom Integration verbindet den Einsatz-Monitor mit Home Assistant für Echtzeit-Alarmbenachrichtigungen.

## Funktionen

- **Sensoren**: Anzahl der Einsätze, letzter Einsatz, aktiver Alarm
- **Echtzeit-Updates**: Via WebSocket für sofortige Benachrichtigungen
- **Alexa-Integration**: Sprachansagen bei Alarm (über HA Alexa Media Player)
- **Licht-Steuerung**: Automatisches Ein-/Ausschalten bei Alarm mit Timer
- **Custom Lovelace Card**: Anzeige der letzten 5 Einsätze

## Installation via HACS

1. HACS öffnen
2. "Integrationen" → Drei-Punkte-Menü → "Benutzerdefinierte Repositories"
3. Repository-URL eingeben und Kategorie "Integration" wählen
4. "Einsatz-Monitor" suchen und installieren
5. Home Assistant neu starten

## Konfiguration

1. Einstellungen → Geräte & Dienste → Integration hinzufügen
2. "Einsatz-Monitor" suchen
3. Server-URL und Token eingeben (aus den App-Einstellungen)

## Optionen

Nach der Einrichtung können Sie unter "Konfigurieren" folgende Optionen setzen:

- **Alexa-Benachrichtigung**: Aktivieren und Alexa-Gerät auswählen
- **Ansage-Text**: Anpassen mit Platzhaltern `{keyword}`, `{unit}`, `{vehicles}`
- **Licht-Alarm**: Lichter auswählen, Farbe und Timer setzen

## Events

Die Integration feuert das Event `einsatz_monitor_new_alarm` bei jedem neuen Alarm. 
Sie können damit eigene Automationen erstellen.

```yaml
automation:
  - alias: "Alarm Benachrichtigung"
    trigger:
      - platform: event
        event_type: einsatz_monitor_new_alarm
    action:
      - service: notify.mobile_app
        data:
          title: "Alarm!"
          message: "{{ trigger.event.data.keyword }}"
```

## Support

Bei Problemen erstellen Sie bitte ein Issue im GitHub Repository.
