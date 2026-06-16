
import unittest
from anti_detect import build_headers

class TestAntiDetect(unittest.TestCase):

    def test_build_headers_chrome(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        headers = build_headers(ua)
        self.assertEqual(headers["User-Agent"], ua)
        self.assertIn("Google Chrome", headers["Sec-CH-UA"])
        self.assertEqual(headers["Sec-CH-UA-Platform"], '"Windows"')

    def test_build_headers_firefox(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
        headers = build_headers(ua)
        self.assertEqual(headers["User-Agent"], ua)
        self.assertNotIn("Sec-CH-UA", headers)
        self.assertIn("Accept", headers)

    def test_build_headers_safari(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
        headers = build_headers(ua)
        self.assertEqual(headers["User-Agent"], ua)
        self.assertIn("Safari", headers["Sec-CH-UA"])
        self.assertEqual(headers["Sec-CH-UA-Platform"], '"macOS"')

if __name__ == "__main__":
    unittest.main()
