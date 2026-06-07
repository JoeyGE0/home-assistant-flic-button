# Flic Button (HACS)

Native Bluetooth integration for **Flic 2**, **Flic Duo**, and **Flic Twist** in Home Assistant — no `flicd` add-on and no dedicated USB Bluetooth dongle required.

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
2. Hold the button for ~7 seconds until the LED flashes (pairing mode)
3. Confirm the discovered device and complete pairing
4. Use the **Button** event entity in automations (single, double, hold, etc.)

Flic buttons only advertise while pressed — keep holding during discovery if HA does not find it immediately.

## Upstream

This custom component packages the in-progress Home Assistant core integration from:

- [home-assistant/core#165260](https://github.com/home-assistant/core/pull/165260)
- [50ButtonsEach/pyflic-ble](https://github.com/50ButtonsEach/pyflic-ble)

When the core integration ships, you can remove this HACS version and use the built-in integration instead.

## License

Integration code follows the Home Assistant core licensing terms. See [LICENSE](LICENSE).
