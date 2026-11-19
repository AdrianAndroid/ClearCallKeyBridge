"""图片必须按设备型号选择，不能把其他设备显示成目标耳机。"""
import unittest

from clearcall200.ui_gui import device_image


class TestDeviceImage(unittest.TestCase):
    def test_known_models_and_unknown(self):
        self.assertEqual(device_image("V98"), ("assets/v98-device.png", 4))
        self.assertEqual(device_image("EDIFIER ClearCall 200"), ("assets/headset-ui.png", 1))
        self.assertEqual(device_image("Keyboard K380"), (None, 1))
        self.assertEqual(device_image(""), (None, 1))


if __name__ == "__main__":
    unittest.main()
