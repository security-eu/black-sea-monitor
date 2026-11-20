import json,subprocess,sys,unittest, pathlib,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def test_json_and_schema(self):
  subprocess.run([sys.executable,str(ROOT/'scripts/validate_data.py')],check=True)
 def test_translations_available(self):
  for lang in ('en','ro','bg'):
   d=json.loads((ROOT/f'i18n/{lang}.json').read_text(encoding='utf8'))
   self.assertIn('about',d);self.assertIn('attribution',d)
 def test_no_google_rss_published(self):
  rows=json.loads((ROOT/'data/statements.json').read_text())
  self.assertFalse(any('news.google.com' in x['url'] for x in rows))
 def test_no_auto_guess_map(self):
  rows=json.loads((ROOT/'data/incidents.json').read_text())
  self.assertFalse(any(x.get('auto_discovered') and x.get('lat') for x in rows))
 def test_unique_ids(self):
  rows=json.loads((ROOT/'data/incidents.json').read_text());self.assertEqual(len(rows),len(set(x['id'] for x in rows)))
if __name__=='__main__':unittest.main()
