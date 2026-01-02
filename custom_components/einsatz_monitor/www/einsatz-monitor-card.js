/**
 * Einsatz-Monitor Card for Home Assistant
 * Displays the last 5 incidents with color-coded rows
 * Version: 1.3.0
 */

class EinsatzMonitorCard extends HTMLElement {
  
  constructor() {
    super();
    this._config = {};
    this._hass = null;
  }

  // Called by Home Assistant when config changes
  setConfig(config) {
    this._config = config || {};
    
    // Set default entity if not provided
    if (!this._config.entity) {
      this._config.entity = 'sensor.letzte_einsatze';
    }
    if (!this._config.title) {
      this._config.title = 'Letzte Einsätze';
    }
  }

  // Called by Home Assistant with state updates
  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  // Card size for layout
  getCardSize() {
    return 4;
  }

  // Format timestamp to German format
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

  // Get icon and color based on incident type
  _getTypeInfo(type) {
    const types = {
      'fire': {
        icon: 'mdi:fire',
        color: '#ef4444',
        bgColor: 'rgba(239, 68, 68, 0.15)'
      },
      'technical': {
        icon: 'mdi:car-emergency',
        color: '#3b82f6',
        bgColor: 'rgba(59, 130, 246, 0.15)'
      },
      'hazmat': {
        icon: 'mdi:hazard-lights',
        color: '#f59e0b',
        bgColor: 'rgba(245, 158, 11, 0.15)'
      }
    };
    
    return types[type] || {
      icon: 'mdi:alert-circle',
      color: '#6b7280',
      bgColor: 'rgba(107, 114, 128, 0.15)'
    };
  }

  // Main render function
  _render() {
    if (!this._hass) return;

    const entityId = this._config.entity || 'sensor.letzte_einsatze';
    const title = this._config.title || 'Letzte Einsätze';
    const stateObj = this._hass.states[entityId];

    // Entity not found
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

    // Get incidents from attributes
    const einsaetze = stateObj.attributes.einsaetze || [];

    let cardContent = '';

    if (einsaetze.length === 0) {
      cardContent = `
        <div style="padding: 20px; text-align: center; color: #6b7280;">
          <ha-icon icon="mdi:check-circle" style="--mdc-icon-size: 48px; color: #10b981;"></ha-icon>
          <p style="margin-top: 10px;">Keine Einsätze vorhanden</p>
        </div>
      `;
    } else {
      cardContent = einsaetze.map((einsatz) => {
        const typeInfo = this._getTypeInfo(einsatz.type);
        const keyword = einsatz.keyword || 'Unbekannt';
        const vehicles = einsatz.vehicles || 'Keine Fahrzeuge';
        const timeStr = this._formatTime(einsatz.timestamp);
        const unit = einsatz.unit || '';
        
        return `
          <div style="
            background: ${typeInfo.bgColor};
            border-left: 4px solid ${typeInfo.color};
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
          ">
            <div style="
              background: ${typeInfo.color};
              border-radius: 50%;
              width: 40px;
              height: 40px;
              display: flex;
              align-items: center;
              justify-content: center;
              flex-shrink: 0;
            ">
              <ha-icon icon="${typeInfo.icon}" style="--mdc-icon-size: 24px; color: white;"></ha-icon>
            </div>
            <div style="flex: 1; min-width: 0;">
              <div style="font-weight: 600; font-size: 1.1em; color: ${typeInfo.color}; margin-bottom: 4px;">
                ${keyword}
              </div>
              ${unit ? `
                <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-bottom: 4px;">
                  <ha-icon icon="mdi:office-building" style="--mdc-icon-size: 14px;"></ha-icon>
                  ${unit}
                </div>
              ` : ''}
              <div style="font-size: 0.9em; color: var(--primary-text-color); margin-bottom: 4px;">
                <ha-icon icon="mdi:truck" style="--mdc-icon-size: 14px;"></ha-icon>
                ${vehicles}
              </div>
              <div style="font-size: 0.8em; color: var(--secondary-text-color);">
                <ha-icon icon="mdi:clock-outline" style="--mdc-icon-size: 14px;"></ha-icon>
                ${timeStr}
              </div>
            </div>
          </div>
        `;
      }).join('');
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

// Register the card
customElements.define('einsatz-monitor-card', EinsatzMonitorCard);

// Register in custom cards list
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'einsatz-monitor-card',
  name: 'Einsatz-Monitor Card',
  description: 'Zeigt die letzten Einsätze mit farblicher Kennzeichnung'
});

console.info('%c EINSATZ-MONITOR-CARD %c v1.3.0 ', 
  'background: #ef4444; color: white; font-weight: bold;', 
  'background: #333; color: white;'
);
