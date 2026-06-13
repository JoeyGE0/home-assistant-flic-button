<div align="center">

# Flic Button

<img src="https://brands.home-assistant.io/flic/icon.png" alt="Flic Button Icon" width="128" height="128">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue)](https://www.home-assistant.io/)

**Native Bluetooth integration for Flic 2, Flic Duo, and Flic Twist in Home Assistant — no flicd add-on and no dedicated USB Bluetooth dongle required.**

[Supported devices](#supported-devices) • [Install](#install-hacs) • [Pair a button](#pair-a-button) • [Upstream](#upstream)

</div>

---

Works with the Home Assistant Bluetooth integration and **ESPHome Bluetooth proxies**.

## Supported devices

| Device | Supported |
|--------|-----------|
| Flic 2 | Yes |
| Flic Duo | Yes |
| Flic Twist | Yes |
| Original Flic 1 | No — still needs [flicd](https://github.com/pschmitt/home-assistant-apps/tree/main/flicd) |

## Requirements

- Home Assistant **2024.12** or newer
- Home Assistant **Bluetooth** integration enabled
- At least one Bluetooth adapter or ESPHome Bluetooth proxy in range of your buttons

## Install (HACS)

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add repository URL: `https://github.com/JoeyGE0/home-assistant-flic-button`
3. Category: **Integration**
4. Search for **Flic Button** and install
5. Restart Home Assistant

## Pair a button

1. **Settings → Devices & services → Add integration → Flic Button**
2. **Factory-reset** the button first if it was ever used with the Flic app or flicd
3. Hold the button for ~**7 seconds** until the LED flashes (pairing mode)
4. Confirm discovery, then on the pair screen **submit while still holding**
5. Stand near your **ESPHome Bluetooth proxy** during pairing — active BLE connections go through it
6. Use the **Button** event entity or **device triggers** in automations (single, double, hold, etc.)

Each device also exposes **Battery** (% and optional voltage), **Connected**, **Signal strength** (dBm while advertising), and optional dial/twist sensors. Battery updates when the button connects — press it near your proxy to refresh the reading.

Flic buttons only advertise while pressed. The integration retries up to 3 times and reconnects automatically when you press the button later.

### ESPHome proxy tips

Pairing needs an **active** Bluetooth connection through your proxy. On the nearest ESP node:

```yaml
esp32:
  framework:
    type: esp-idf

esp32_ble:
  connection_timeout: 20s

bluetooth_proxy:
  active: true
  connection_slots: 3
```

## Upstream

This custom component packages the in-progress Home Assistant core integration from:

- [home-assistant/core#165260](https://github.com/home-assistant/core/pull/165260)
- [50ButtonsEach/pyflic-ble](https://github.com/50ButtonsEach/pyflic-ble)

When the core integration ships, you can remove this HACS version and use the built-in integration instead.

## License

Integration code follows the Home Assistant core licensing terms. See [LICENSE](LICENSE).
