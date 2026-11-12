"""Run with: python -m unittest discover -s scripts -p test_dcfanki.py -v"""
import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tiny_pdf(path):
    """Synthetic two-page PDF: normal, faux-bold, blue underlined, and red."""
    content = b'BT /F1 12 Tf 1 0 0 1 30 260 Tm (Normal) Tj 2 Tr 0.3 w 1 0 0 1 30 230 Tm (Bold) Tj 0 Tr 0 0.439 0.753 rg 1 0 0 1 30 200 Tm (Term) Tj 1 0 0 rg 1 0 0 1 30 170 Tm (Essay) Tj ET 0 0.439 0.753 RG 0.6 w 30 198 m 58 198 l S'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>']
    result = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    offset = len(result)
    result += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:])
    result += f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF'.encode()
    path.write_bytes(result)


class DcfAnkiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extract = load('extract_pdf')
        cls.build = load('build_apkg')

    def plan(self):
        return {'source_id': 'synthetic-notes-1', 'deck': '测试笔记::测试章', 'scope': {'label': '测试章', 'pages': [1], 'confirmed': True}, 'cards': [
            {'id': 'b1', 'kind': 'cloze', 'text': '阶段：{{c1::8岁以后}}；作用：{{c2::升温}}。'},
            {'id': 't1', 'kind': 'term', 'front': 'test term', 'back': '<b>测试名词</b><br>用于测试的中文解释。'},
            {'id': 'e1', 'kind': 'essay', 'front': '简述测试变化。', 'back': '<ol><li>第一点。</li><li>第二点。</li></ol>'}]}

    def test_scope_and_pdf_styles(self):
        self.assertEqual(self.extract.parse_pages('2,4-5,2'), [2, 4, 5])
        with self.assertRaises(ValueError): self.extract.parse_pages('0-2')
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'input.pdf'; tiny_pdf(pdf)
            result = self.extract.extract(pdf, [2])
            self.assertEqual([p['page'] for p in result['pages']], [2])
            spans = [s for line in result['pages'][0]['lines'] for s in line['spans']]
            self.assertEqual({s['kind']: s['text'] for s in spans}, {'black_bold': 'Bold', 'blue': 'Term', 'red': 'Essay'})
            self.assertTrue(next(s for s in spans if s['kind'] == 'blue')['underlined'])
            cropped = self.extract.extract(pdf, [1], first_top=60, last_bottom=115)
            text = ''.join(line['text'] for line in cropped['pages'][0]['lines'])
            self.assertNotIn('Normal', text); self.assertNotIn('Essay', text)
            with self.assertRaises(ValueError): self.extract.extract(pdf, [3])

    def test_package_answers_no_metadata_and_stable_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); output = folder / 'cards.apkg'
            summary = self.build.build(self.plan(), output)
            self.assertEqual(summary, {'notes': 3, 'cards': 4, 'cloze': 2, 'term': 1, 'essay': 1})
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ['cards.apkg'])
            with zipfile.ZipFile(output) as z:
                self.assertIsNone(z.testzip()); db = folder / 'test.anki2'; db.write_bytes(z.read('collection.anki2'))
            with closing(sqlite3.connect(db)) as c:
                models = json.loads(c.execute('select models from col').fetchone()[0])
                self.assertEqual(c.execute('select count(*) from cards').fetchone()[0], 4)
                guids = c.execute('select guid from notes order by guid').fetchall()
                for mid, fields, tags in c.execute('select mid,flds,tags from notes'):
                    self.assertFalse(tags.strip())
                    model = models[str(mid)]; template = model['tmpls'][0]
                    self.assertNotIn('Extra', template['afmt']); self.assertNotIn('source', template['afmt'])
                    if model['type'] == 0:
                        front, back = fields.split('\x1f')
                        rendered = template['afmt'].replace('{{FrontSide}}', front).replace('{{Back}}', back)
                        self.assertIn(back, rendered); self.assertNotIn('{{', rendered)
                self.assertEqual(c.execute('select count(*) from notes where flds like ?', ('%来源：%',)).fetchone()[0], 0)
            with self.assertRaises(FileExistsError): self.build.build(self.plan(), output)
            self.build.build(self.plan(), output, replace=True)
            with zipfile.ZipFile(output) as z: db.write_bytes(z.read('collection.anki2'))
            with closing(sqlite3.connect(db)) as c: self.assertEqual(guids, c.execute('select guid from notes order by guid').fetchall())

    def test_invalid_input_never_writes_package(self):
        variants = []
        for edit in ['unconfirmed', 'heading', 'tags', 'empty_answer', 'invisible_answer', 'invisible_cloze', 'chinese_front', 'script', 'bad_cloze', 'duplicate', 'outside_scope']:
            p = copy.deepcopy(self.plan())
            if edit == 'unconfirmed': p['scope']['confirmed'] = False
            elif edit == 'heading': p['cards'][0]['role'] = 'heading'
            elif edit == 'tags': p['cards'][0]['tags'] = ['extra']
            elif edit == 'empty_answer': p['cards'][1]['back'] = '<br>'
            elif edit == 'invisible_answer': p['cards'][1]['back'] = '&#8203;'
            elif edit == 'invisible_cloze': p['cards'][0]['text'] = '测试{{c1::\u200b}}'
            elif edit == 'chinese_front': p['cards'][1]['front'] = '英文名词（中文提示）'
            elif edit == 'script': p['cards'][1]['back'] = '<script>alert(1)</script>'
            elif edit == 'bad_cloze': p['cards'][0]['text'] = '{{c1::one}} {{c3::three}}'
            elif edit == 'duplicate': p['cards'][1]['id'] = 'b1'
            else: p['scope']['pages'] = [0]
            variants.append((edit, p))
        with tempfile.TemporaryDirectory() as tmp:
            for edit, p in variants:
                with self.subTest(edit=edit), self.assertRaises(ValueError):
                    self.build.build(p, Path(tmp) / 'invalid.apkg')
                self.assertFalse((Path(tmp) / 'invalid.apkg').exists())


if __name__ == '__main__':
    unittest.main()
