#!/usr/bin/env python3
"""Build a HolyIOT 21017 USB BLE connectivity firmware from patched nRF5 SDK 15.3.

This intentionally creates a separate project and leaves the regular PCA10059
project untouched. The Nordic SDK is downloaded/patched by this repository's
existing CMake setup before this script runs.
"""
import argparse
import shutil
import subprocess
from pathlib import Path

FEM_SOURCE = r"""
/* HolyIOT 21017: active-high two-control-pin RF front end.
 * Pins are taken from jitingcn/SlimeVR-Tracker-nRF-Receiver (dev):
 *   CTX/TXEN = P0.24; CRX/RXEN = P0.22.
 * SoftDevice owns PPI channels 0/1 and GPIOTE channel 0 after opt_set.
 * Do not independently toggle these pins while Bluetooth is active.
 */
#define HOLYIOT_21017_PA_PIN 24
#define HOLYIOT_21017_LNA_PIN 22

static bool m_holyiot_fem_ready;
static bool m_holyiot_fem_error;

static void holyiot_21017_fem_gpio_init(void)
{
    /* Inactive state while BLE/SoftDevice starts up. */
    nrf_gpio_pin_clear(HOLYIOT_21017_PA_PIN);
    nrf_gpio_pin_clear(HOLYIOT_21017_LNA_PIN);
    nrf_gpio_cfg_output(HOLYIOT_21017_PA_PIN);
    nrf_gpio_cfg_output(HOLYIOT_21017_LNA_PIN);
}

static void holyiot_21017_fem_enable_if_ready(void)
{
    if (m_holyiot_fem_ready || m_holyiot_fem_error || !nrf_sdh_is_enabled())
    {
        return;
    }

    /* The host enables BLE through serialization, not in main().
     * Called after processing each incoming serial command, so PA/LNA can
     * be enabled immediately after the host enables the BLE stack.
     */
    ble_opt_t opt = {0};
    opt.common_opt.pa_lna.pa_cfg.enable       = 1;
    opt.common_opt.pa_lna.pa_cfg.active_high  = 1;
    opt.common_opt.pa_lna.pa_cfg.gpio_pin     = HOLYIOT_21017_PA_PIN;
    opt.common_opt.pa_lna.lna_cfg.enable      = 1;
    opt.common_opt.pa_lna.lna_cfg.active_high = 1;
    opt.common_opt.pa_lna.lna_cfg.gpio_pin    = HOLYIOT_21017_LNA_PIN;
    opt.common_opt.pa_lna.ppi_ch_id_set       = 0;
    opt.common_opt.pa_lna.ppi_ch_id_clr       = 1;
    opt.common_opt.pa_lna.gpiote_ch_id        = 0;

    ret_code_t result = sd_ble_opt_set(BLE_COMMON_OPT_PA_LNA, &opt);
    if (result == NRF_SUCCESS)
    {
        m_holyiot_fem_ready = true;
        NRF_LOG_INFO("HolyIOT 21017 FEM enabled (TX=P0.24 RX=P0.22)");
    }
    else if (result != NRF_ERROR_INVALID_STATE &&
             result != NRF_ERROR_SOFTDEVICE_NOT_ENABLED)
    {
        /* Fail closed rather than switching the front-end incorrectly. */
        m_holyiot_fem_error = true;
        NRF_LOG_ERROR("HolyIOT 21017 PA/LNA opt_set failed: %u", result);
    }
}

"""

def single_replace(source: str, before: str, after: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError("Expected exactly one SDK source anchor (found %d): %r" %
                           (count, before[:90]))
    return source.replace(before, after, 1)


def prepare(sdk: Path) -> Path:
    root = sdk / "examples" / "connectivity" / "ble_connectivity"
    stock = root / "pca10059" / "ser_s140_usb_hci"
    custom = root / "pca10060" / "ser_s140_usb_hci"
    main_path = root / "main.c"
    if not stock.is_dir() or not main_path.is_file():
        raise RuntimeError("SDK 15.3 is missing its patched PCA10059 USB/S140 project: " +
                           str(stock))
    # Always regenerate from the untouched stock project. This also avoids
    # accidentally mixing different SDK versions in a reused TMP directory.
    if custom.exists():
        shutil.rmtree(custom)
    shutil.copytree(stock, custom)

    main = main_path.read_text(encoding="utf-8")
    # Patched upstream detects a PCA10056 by QSPI and otherwise assumes a
    # PCA10059: on HolyIOT P0.24 is TXEN, NOT a pin-reset bridge.
    main = single_replace(main, "#define BOARD_DETECTION 1",
                          "#define BOARD_DETECTION 0 /* no PCA QSPI / reset probe */")
    main = single_replace(main, '#include "ser_config.h"',
                          '#include "ser_config.h"\n#include "ble.h"\n#include "nrf_gpio.h"')
    main = single_replace(main, "static void on_idle(void)", FEM_SOURCE +
                          "\nstatic void on_idle(void)")
    main = single_replace(main, "    uint32_t err_code = NRF_SUCCESS;",
                          "    uint32_t err_code = NRF_SUCCESS;\n"
                          "    holyiot_21017_fem_gpio_init();")
    main = single_replace(main, "        on_idle();",
                          "        holyiot_21017_fem_enable_if_ready();\n"
                          "        on_idle();")
    (root / "main_holyiot_21017.c").write_text(main, encoding="utf-8")

    makefile = custom / "armgcc" / "Makefile"
    make_text = makefile.read_text(encoding="utf-8")
    make_text = single_replace(make_text, "$(PROJ_DIR)/main.c",
                               "$(PROJ_DIR)/main_holyiot_21017.c")
    makefile.write_text(make_text, encoding="utf-8")
    return custom / "armgcc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--make", default="make")
    parser.add_argument("--mergehex", default="mergehex")
    parser.add_argument("--prepare-only", action="store_true",
                        help="Prepare isolated SDK project without building")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    sdk = args.sdk_root.resolve()
    armgcc = prepare(sdk)
    print("Prepared independent HolyIOT 21017 project:", armgcc)
    if args.prepare_only:
        return

    subprocess.run([args.make, "-C", str(armgcc), "-j", str(args.jobs)],
                   check=True)
    application = armgcc / "_build" / "nrf52840_xxaa.hex"
    sd_candidates = list((sdk / "components" / "softdevice" / "s140" / "hex").glob(
        "s140_nrf52_6.1.1_softdevice.hex"))
    if not application.is_file() or len(sd_candidates) != 1:
        raise RuntimeError("Missing application or S140 v6.1.1 SoftDevice HEX")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app_out = output / "holyiot_21017_usb_s140_6.1.1_application.hex"
    merged = output / "holyiot_21017_usb_s140_6.1.1_sd_app.hex"
    shutil.copyfile(application, app_out)
    subprocess.run([args.mergehex, "-m", str(app_out), str(sd_candidates[0]),
                    "-o", str(merged)], check=True)
    print("Application HEX:", app_out)
    print("Merged HEX (SWD, NOT a USB DFU ZIP):", merged)
    print("NOTE: no DFU ZIP generated; verify bootloader type and signing first.")


if __name__ == "__main__":
    main()
