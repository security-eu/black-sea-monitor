import json,sys,re,datetime
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data';SCHEMA=ROOT/'schemas'
def check(filename,schema):
 data=json.loads((D/filename).read_text(encoding='utf8'))
 validator=Draft202012Validator(json.loads((SCHEMA/schema).read_text(encoding='utf8')))
 errors=list(validator.iter_errors(data))
 if errors:
  for e in errors[:8]:print(filename, list(e.path),e.message,file=sys.stderr)
  raise ValueError(f'{filename} invalid: {len(errors)} errors')
 return data
statements=check('statements.json','statements.schema.json')
incidents=check('incidents.json','incidents.schema.json')
ids=set()
for item in incidents:
 if item['id'] in ids:raise ValueError('Duplicate incident id: '+item['id'])
 ids.add(item['id']);datetime.date.fromisoformat(item['date'])
 if item.get('auto_discovered') and (item.get('lat') or item.get('lon')):raise ValueError('Auto-discovered incident should not be auto-mapped')
 if item.get('country') not in ('Romania','Bulgaria','Ukraine'):raise ValueError('Unsupported country')
for row in statements:
 datetime.date.fromisoformat(row['date'])
 if 'news.google.com' in row['url']:raise ValueError('Google News RSS is not a direct published source: '+row['url'])
 # An institutional source can be present while still awaiting editorial review; the UI hides those by default.
print('Validated:',len(statements),'statements;',len(incidents),'incidents')
