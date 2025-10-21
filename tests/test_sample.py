"""示例测试用例，确保测试流程可以运行。"""

import unittest


class SampleTestCase(unittest.TestCase):
    def test_basic_arithmetic(self) -> None:
        self.assertEqual(1 + 1, 2)

    def test_string_contains(self) -> None:
        self.assertIn("网易", "网易云音乐")


if __name__ == "__main__":
    unittest.main()
