"""Host-only smoke checks for the HolyIOT 21017 SDK project generator."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "hex" / "holyiot_21017" / "build.py"
spec = importlib.util.spec_from_file_location("holyiot_build", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BuildHelperTest(unittest.TestCase):
    def test_isolated_copy_and_source_transformation(self):
        with tempfile.TemporaryDirectory() as work:
            sdk = Path(work)
            project = sdk / "examples" / "connectivity" / "ble_connectivity"
            original = project / "pca10059" / "ser_s140_usb_hci" / "armgcc"
            original.mkdir(parents=True)
            makefile = original / "Makefile"
            makefile.write_text("SRC_FILES += $(PROJ_DIR)/main.c \\\n", encoding="utf-8")
            source = ('#include "ser_config.h"\n'
                      '#define BOARD_DETECTION 1\n'
                      'static void on_idle(void) {}\n'
                      'int main(void) {\n'
                      '    uint32_t err_code = NRF_SUCCESS;\n'
                      '    while (1) {\n'
                      '        on_idle();\n'
                      '    }\n'
                      '}\n')
            (project / "main.c").write_text(source, encoding="utf-8")
            result = mod.prepare(sdk)
            self.assertEqual(result.parent.parent.parent.name, "ser_s140_usb_hci")
            self.assertEqual(makefile.read_text(encoding="utf-8"),
                             "SRC_FILES += $(PROJ_DIR)/main.c \\\n")
            self.assertIn("main_holyiot_21017.c",
                          (result / "Makefile").read_text(encoding="utf-8"))
            generated = (project / "main_holyiot_21017.c").read_text(
                encoding="utf-8")
            self.assertIn("#define BOARD_DETECTION 0", generated)
            self.assertIn("#define HOLYIOT_21017_PA_PIN 24", generated)
            self.assertIn("#define HOLYIOT_21017_LNA_PIN 22", generated)
            self.assertIn("sd_ble_opt_set(BLE_COMMON_OPT_PA_LNA, &opt)", generated)
            self.assertIn("holyiot_21017_fem_enable_if_ready();", generated)
            self.assertEqual((project / "main.c").read_text(encoding="utf-8"),
                             source)


if __name__ == "__main__":
    unittest.main()
