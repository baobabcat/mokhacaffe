import json
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PAGE = PUBLIC / "coffee-ratio-calculator" / "index.html"
PAGE_PATH = "/coffee-ratio-calculator/"


class RatioCalculatorTests(unittest.TestCase):
    def test_calculation_module_handles_both_directions_and_validation(self):
        module_uri = (PUBLIC / "assets" / "ratio-calculator.mjs").as_uri()
        script = f"""
          import {{ calculateCoffee, calculateWater }} from {json.dumps(module_uri)};
          const results = {{
            coffee: calculateCoffee(320, 16),
            rounded: calculateCoffee(500, 17),
            water: calculateWater(20, 16),
          }};
          try {{ calculateCoffee(0, 16); }} catch (error) {{ results.zero = error.name; }}
          try {{ calculateWater(20, Number.NaN); }} catch (error) {{ results.nan = error.name; }}
          try {{ calculateCoffee(20, 0.5); }} catch (error) {{ results.smallRatio = error.name; }}
          try {{ calculateWater(1e308, 1e308); }} catch (error) {{ results.overflow = error.name; }}
          try {{ calculateWater(1e307, 17); }} catch (error) {{ results.roundingOverflow = error.name; }}
          try {{ calculateCoffee(1e308, 1); }} catch (error) {{ results.coffeeOverflow = error.name; }}
          console.log(JSON.stringify(results));
        """
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "coffee": 20,
                "rounded": 29.4,
                "water": 320,
                "zero": "RangeError",
                "nan": "RangeError",
                "smallRatio": "RangeError",
                "overflow": "RangeError",
                "roundingOverflow": "RangeError",
                "coffeeOverflow": "RangeError",
            },
        )

    def test_page_is_indexable_connected_and_measurable(self):
        html = PAGE.read_text()
        self.assertIn("<title>Coffee Ratio Calculator | Mokha Caffè</title>", html)
        self.assertIn(
            '<link rel="canonical" href="https://mokhacaffe.com/coffee-ratio-calculator/">',
            html,
        )
        self.assertIn('id="ratio-form"', html)
        self.assertIn('id="result" aria-live="polite"', html)
        self.assertIn('src="/assets/ratio-calculator-page.mjs"', html)
        self.assertIn("gtag('config', 'G-HJNKHJZZLL');", html)

        hub = (PUBLIC / "better-coffee-at-home" / "index.html").read_text()
        self.assertIn(f'href="{PAGE_PATH}"', hub)

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
        self.assertIn("https://mokhacaffe.com" + PAGE_PATH, urls)

        page_script = (PUBLIC / "assets" / "ratio-calculator-page.mjs").read_text()
        self.assertIn("ratio_calculation", page_script)
        self.assertIn("calculation_direction", page_script)
        self.assertNotIn("knownAmount", page_script.split("window.gtag", 1)[-1])


if __name__ == "__main__":
    unittest.main()