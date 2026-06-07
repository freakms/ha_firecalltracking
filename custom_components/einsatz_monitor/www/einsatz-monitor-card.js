/**
 * Einsatz-Monitor Card for Home Assistant
 * Displays the last 4 incidents as a 2x2 grid with color-coded cards
 * Version: 1.4.17
 */

class EinsatzMonitorCard extends HTMLElement {

  setConfig(config) {
    if (!config) {
      throw new Error('Ungültige Konfiguration');
    }

    const defaultConfig = {
      entity: 'sensor.letzte_einsatze',
      title: 'Letzte Einsätze'
    };

    Object.assign(this, {
      config: Object.assign({}, defaultConfig, config)
    });
  }

  set hass(hass) {
    Object.assign(this, { _hass: hass });
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _formatTime(timestamp) {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return String(timestamp);
    }
  }

  _getTypeInfo(type) {
    const types = {
      'fire': {
        icon: 'mdi:fire',
        color: '#ef4444',
        bgColor: 'rgba(239, 68, 68, 0.12)',
        borderColor: 'rgba(239, 68, 68, 0.4)'
      },
      'technical': {
        icon: 'mdi:car-emergency',
        color: '#3b82f6',
        bgColor: 'rgba(59, 130, 246, 0.12)',
        borderColor: 'rgba(59, 130, 246, 0.4)'
      },
      'hazmat': {
        icon: 'mdi:hazard-lights',
        color: '#f59e0b',
        bgColor: 'rgba(245, 158, 11, 0.12)',
        borderColor: 'rgba(245, 158, 11, 0.4)'
      }
    };

    return types[type] || {
      icon: 'mdi:alert-circle',
      color: '#6b7280',
      bgColor: 'rgba(107, 114, 128, 0.12)',
      borderColor: 'rgba(107, 114, 128, 0.4)'
    };
  }

  _renderGridItem(einsatz, index) {
    const typeInfo = this._getTypeInfo(einsatz.type);
    const keyword = einsatz.keyword || 'Unbekannt';
    const vehicles = einsatz.vehicles || 'Keine Fahrzeuge';
    const timeStr = this._formatTime(einsatz.timestamp);
    const unit = einsatz.unit || '';

    return `
      <div style="
        background: ${typeInfo.bgColor};
        border: 1px solid ${typeInfo.borderColor};
        border-top: 3px solid ${typeInfo.color};
        border-radius: 10px;
        padding: 14px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-width: 0;
      ">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div style="
            background: ${typeInfo.color};
            border-radius: 50%;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
          ">
            <ha-icon icon="${typeInfo.icon}" style="--mdc-icon-size: 20px; color: white;"></ha-icon>
          </div>
          <div style="
            font-weight: 700;
            font-size: 1em;
            color: ${typeInfo.color};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          ">${keyword}</div>
        </div>

        ${unit ? `
          <div style="font-size: 0.78em; color: var(--secondary-text-color); display: flex; align-items: center; gap: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
            <ha-icon icon="mdi:office-building" style="--mdc-icon-size: 13px; flex-shrink: 0;"></ha-icon>
            <span style="overflow: hidden; text-overflow: ellipsis;">${unit}</span>
          </div>
        ` : ''}

        <div style="font-size: 0.82em; color: var(--primary-text-color); display: flex; align-items: center; gap: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
          <ha-icon icon="mdi:truck" style="--mdc-icon-size: 13px; flex-shrink: 0;"></ha-icon>
          <span style="overflow: hidden; text-overflow: ellipsis;">${vehicles}</span>
        </div>

        <div style="font-size: 0.75em; color: var(--secondary-text-color); display: flex; align-items: center; gap: 4px; margin-top: auto;">
          <ha-icon icon="mdi:clock-outline" style="--mdc-icon-size: 13px; flex-shrink: 0;"></ha-icon>
          ${timeStr}
        </div>
      </div>
    `;
  }

  _render() {
    if (!this._hass) return;

    const entityId = this.config.entity || 'sensor.letzte_einsatze';
    const title = this.config.title || 'Letzte Einsätze';
    const stateObj = this._hass.states[entityId];

    if (!stateObj) {
      this.innerHTML = `
        <ha-card header="${title}">
          <div style="padding: 16px; color: #ef4444;">
            <ha-icon icon="mdi:alert" style="margin-right: 8px;"></ha-icon>
            Entity nicht gefunden: ${entityId}
          </div>
        </ha-card>
      `;
      return;
    }

    const allEinsaetze = stateObj.attributes.einsaetze || [];
    const einsaetze = allEinsaetze.slice(0, 4);

    let cardContent = '';

    if (einsaetze.length === 0) {
      cardContent = `
        <div style="padding: 20px; text-align: center; color: #6b7280;">
          <ha-icon icon="mdi:check-circle" style="--mdc-icon-size: 48px; color: #10b981;"></ha-icon>
          <p style="margin-top: 10px;">Keine Einsätze vorhanden</p>
        </div>
      `;
    } else {
      const items = einsaetze.map((e, i) => this._renderGridItem(e, i)).join('');
      cardContent = `
        <div style="
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        ">
          ${items}
        </div>
      `;
    }

    this.innerHTML = `
      <ha-card header="${title}">
        <div style="padding: 16px;">
          ${cardContent}
        </div>
      </ha-card>
    `;
  }
}

customElements.define('einsatz-monitor-card', EinsatzMonitorCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'einsatz-monitor-card',
  name: 'Einsatz-Monitor Card',
  description: 'Zeigt die letzten 4 Einsätze im Grid-Design mit farblicher Kennzeichnung'
});

console.info('%c EINSATZ-MONITOR-CARD %c v1.4.17 ',
  'background: #ef4444; color: white; font-weight: bold;',
  'background: #333; color: white;'
);
