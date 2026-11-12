"""Run the native locale helpers and English admin against real source, offline."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'firmware/custom_components/gym_native'


class LanguageTests(unittest.TestCase):
    def test_native_progress_decimals_and_admin_behaviour_in_english(self):
        source = r'''
#include "ui_text.h"
#include "workout_progress.h"
#include "admin_page.h"
#include <cassert>
#include <iostream>
using namespace esphome::gym_native;
int main() {
  UiText nb;
  UiText en;
  en.english = true;
  assert(nb.tr("Registrer sett", "Log set") == std::string("Registrer sett"));
  assert(en.tr("Registrer sett", "Log set") == std::string("Log set"));
  assert(nb.decimal("12.5 kg") == "12,5 kg");
  assert(en.decimal("12,5 kg") == "12.5 kg");
  WorkoutProgress progress;
  progress.work_total = 3;
  progress.next_row = 0;
  progress.next_ordinal = 1;
  progress.next_side = 2;
  assert(progress.next_caption(nb) == "Sett 1 av 3 · Høyre");
  assert(progress.next_caption(en) == "Set 1 of 3 · Right");
  progress.next_row = -1;
  assert(progress.next_caption(en) == "Complete");
  assert(admin_page(nb) == ADMIN_PAGE);
  const auto page = admin_page(en);
  assert(page.find("lang=\"en\"") != std::string::npos);
  assert(page.find("Display settings") != std::string::npos);
  assert(page.find("Skjerminnstillinger") == std::string::npos);
  assert(page.find("/admin/diagnostics.json") != std::string::npos);
  std::cout << page;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'locale.cpp').write_text(source)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(COMPONENT), str(folder / 'locale.cpp'),
                            '-o', str(folder / 'locale')], check=True)
            html = folder / 'admin-en.html'
            html.write_bytes(subprocess.check_output([str(folder / 'locale')]))
            subprocess.run(['node', 'tests/admin-client.cjs'], cwd=ROOT, check=True,
                           env={**os.environ, 'ADMIN_HTML_PATH': str(html),
                                'PANEL_TEST_LANGUAGE': 'en'})


if __name__ == '__main__':
    unittest.main()
