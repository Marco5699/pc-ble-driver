# HolyIOT 21017 — nRF52840 USB BLE Connectivity (experimental)

This board port targets **nRF Connect for Desktop → Bluetooth Low Energy**
using **pc-ble-driver's USB CDC serialization**, not Windows' system Bluetooth
HCI driver. It derives a separate build from the SDK 15.3.0
`pca10059/ser_s140_usb_hci` project.

Hardware reference:
[jitingcn/SlimeVR-Tracker-nRF-Receiver](https://github.com/jitingcn/SlimeVR-Tracker-nRF-Receiver/tree/dev/boards/holyiot/holyiot_21017).

| Feature | HolyIOT 21017 |
| --- | --- |
| SoC | nRF52840 |
| USB | Native USB CDC (pc-ble-driver serialized SoftDevice) |
| SoftDevice | S140 6.1.1 / BLE API v6 |
| RF front-end TX control | P0.24, active HIGH |
| RF front-end RX control | P0.22, active HIGH |
| SoftDevice FEM control | `BLE_COMMON_OPT_PA_LNA`, PPI channels 0/1, GPIOTE channel 0 |
| QSPI board autodetection | Disabled |
| Nordic PCA10056/PCA10059 self-reset USB DFU trigger | Disabled |

The jitingcn Zephyr board describes the FEM as a generic two-control-pin FEM
with nominal TX gain 22 dB and RX gain 12 dB. This port reuses the confirmed
**pins and polarity**, **not** Zephyr/MPSL's FEM backend or a verified
transmit-power calibration.

## Build

Prepare this repository using the [upstream connectivity build instructions](
../../README.md#compiling-connectivity-hex-files). Required tools include:

- Python 3, CMake, Git, GNU Make, mergehex, and *legacy* Nordic `nrfutil`.
- GNU Arm Embedded **7.3.1** (the SDK 15.3.0 Makefiles/toolchain check).
- `GCCARMEMB_TOOLCHAIN_PATH` and `GNUARMEMB_TOOLCHAIN_PATH` pointing to
  the GCC toolchain installation (the original build expects these names).
- `TMP` pointing to a writable temporary folder (especially on Linux).

Then use this port's dedicated target. **Do not use `compile_connectivity`
for the HolyIOT image**; that target still builds the original Nordic boards.

```sh
git clone https://github.com/Marco5699/pc-ble-driver.git
cd pc-ble-driver
git checkout feat/holyiot-21017-connectivity
cmake -S . -B build -DCOMPILE_CONNECTIVITY=ON -DCONNECTIVITY_VERSION=1.0.0
cmake --build build --target compile_holyiot_21017
```

CMake configures/downloads and patches the original SDK 11 and 15 trees
before the dedicated target builds the HolyIOT version. The Python helper
creates a **separate** `pca10060/ser_s140_usb_hci` project in the SDK cache,
and emits a customized `main_holyiot_21017.c`. It does not overwrite the
original `pca10059` Makefile or `main.c`.

The target writes:

```
hex/sd_api_v6/holyiot_21017/
  holyiot_21017_usb_s140_6.1.1_application.hex
  holyiot_21017_usb_s140_6.1.1_sd_app.hex
```

The first is an *application-only* HEX; the second is SoftDevice + application
for SWD workflows. **Neither HEX is a USB DFU package**. A DFU ZIP has to
match your bootloader's format, application flash address, security
requirements/signature, SoftDevice requirements and application version.


## BLE Standalone 4.0.4 / SoftDevice API 5

The Nordic Bluetooth Low Energy Standalone 4.0.4 bundled connectivity image
uses **SoftDevice API v5** (historically `ble-connectivity 4.1.4`).
If the log reports API v5, test this separate build rather than the original
S140/API v6 image:

```sh
cmake --build build --target compile_holyiot_21017_api5
```

Produces:

```
hex/sd_api_v5/holyiot_21017/
  holyiot_21017_usb_s132_5.1.0_application.hex
  holyiot_21017_usb_s132_5.1.0_sd_app.hex
```

This follows the patched SDK's nRF52840 / S132 API 5 USB project. The
external FEM pins remain TXEN P0.24 and RXEN P0.22. USB Connectivity is
**not the same** as a Windows-native HCI Bluetooth adapter.

**The version shown in a PC tool may reflect its firmware registry/expected
image, not definitively the image currently running on a custom bootloader.**
Validate the actual flash/application/SoftDevice before overwriting anything.
This API5 build has passed ARM GCC compilation and HEX merge but has not been
validated on physical HolyIOT 21017 hardware. As with API6, neither HEX is a
signed USB DFU update package.

## RF behavior

- TXEN and RXEN are both low at startup.
- After the PC host enables the BLE stack through serialization, firmware
  configures SoftDevice's `BLE_COMMON_OPT_PA_LNA` to switch pins automatically
  around radio TX/RX events. It does **not** toggle them with CPU GPIO timing.
- The board port disables Nordic's QSPI board autodetection. That routine uses
  P0.24 for PCA10056 reset, which would conflict with HolyIOT's TXEN pin.
- The Nordic USB DFU trigger is also disabled; this port intentionally does
  not provide a firmware-triggered jump to your existing custom DFU loader.
- No LED logic or pin-reset bridge from the Nordic PCA10059 board is used.
- **Transmit power:** the external PA adds gain. Do not assume that a
  host-selected 0 dBm means 0 dBm at the antenna. Start with low RF power
  and measure conducted/radiated output before normal use.
- This is a first-pass port and **has not been hardware-validated**.
  Verify FEM timing, RX sensitivity, BLE scanning and stable USB enumeration.

## DFU warning for Dawn Receiver 2

If your board currently enumerates as `Dawn Receiver 2 DFU`, that indicates
a custom bootloader/interface is running. It does **not** prove compatibility
with Nordic Secure DFU ZIPs or with S140 6.1.1. If it uses MCUboot or
application-signature validation, a Nordic nrfutil package will be rejected.
Do not erase the chip or overwrite the bootloader. First identify the actual
bootloader and signing key, or use a known-good SWD recovery path.

Also prevent nRF Connect Bluetooth Low Energy Standalone from automatically
flashing a generic board firmware over this custom one.

## Implementation

The build helper is [`build.py`](build.py). It applies only minimal
board-specific changes to the generated SDK project, keeping the upstream
`pc-ble-driver` and USB serialization protocol intact.

**Verification status:** build helper and CMake integration are committed;
firmware compilation, USB DFU, RF characteristics, and BLE behavior still
require testing with the toolchain and physical device.
