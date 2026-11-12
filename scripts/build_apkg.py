"""Build a clean Anki package from an agent-reviewed card plan."""
import argparse
import hashlib
import html
import json
import re
import sqlite3
import tempfile
import unicodedata
import zipfile
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

import genanki

CLOZE = re.compile(r'\{\{c([1-9]\d*)::([^{}]+)\}\}')
CSS = '.card { font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 22px; line-height: 1.7; text-align: left; padding: 16px; } .cloze { color: #1675bd; font-weight: bold; } table { border-collapse: collapse; width: 100%; font-size: 18px; } th, td { border: 1px solid #aaa; padding: 6px; }'


class AnswerHTML(HTMLParser):
    allowed = {'b', 'strong', 'i', 'em', 'p', 'div', 'br', 'ol', 'ul', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'sub', 'sup'}

    def __init__(self):
        super().__init__(); self.text = []; self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed or any(k not in ('colspan', 'rowspan') or tag not in ('td', 'th') or not (v or '').isdigit() or not 1 <= int(v) <= 20 for k, v in attrs):
            raise ValueError('答案HTML包含不支持的标签或属性')
        if tag != 'br': self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag != 'br': raise ValueError('仅br可使用自闭合标签')
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError('答案HTML标签未正确闭合')

    def handle_data(self, data): self.text.append(data)


def visible_text(value):
    return any(unicodedata.category(char)[0] in 'LNPS' for char in value)


def plain(value, label):
    if not isinstance(value, str) or not visible_text(value) or '\x00' in value or '\x1f' in value or '\ufffd' in value or '(cid:' in value:
        raise ValueError(f'{label}必须是非空且无乱码的文本')
    return value


def stable_id(value):
    return 1_000_000_000 + int(hashlib.sha256(value.encode()).hexdigest()[:12], 16) % 1_000_000_000


def validate(plan):
    if not isinstance(plan, dict) or set(plan) != {'source_id', 'deck', 'scope', 'cards'}:
        raise ValueError('计划字段必须为source_id、deck、scope、cards')
    source = plain(plan['source_id'], 'source_id'); deck = plain(plan['deck'], 'deck')
    scope = plan['scope']
    if not isinstance(scope, dict) or set(scope) != {'label', 'pages', 'confirmed'} or scope['confirmed'] is not True:
        raise ValueError('必须先取得用户明确的章节范围确认')
    plain(scope['label'], 'scope.label')
    pages = scope['pages']
    if not isinstance(pages, list) or not pages or any(type(p) is not int or p < 1 for p in pages) or pages != sorted(set(pages)):
        raise ValueError('scope.pages必须为排序且不重复的PDF正整数页码')
    if not isinstance(plan['cards'], list) or not plan['cards']:
        raise ValueError('cards不能为空')
    records = []; seen = set(); totals = {'cloze': 0, 'term': 0, 'essay': 0}
    for card in plan['cards']:
        if not isinstance(card, dict): raise ValueError('每张卡必须为对象')
        kind = card.get('kind')
        expected = {'id', 'kind', 'text'} if kind == 'cloze' else {'id', 'kind', 'front', 'back'}
        if kind not in totals or set(card) != expected:
            raise ValueError('只接受cloze/term/essay及其必要字段；不接受标题、标签或额外说明字段')
        ident = plain(card['id'], 'card.id')
        if ident in seen: raise ValueError('card.id重复')
        seen.add(ident)
        if kind == 'cloze':
            text = plain(card['text'], 'cloze.text'); matches = list(CLOZE.finditer(text))
            indices = [int(m[1]) for m in matches]
            if not indices or indices != list(range(1, len(indices) + 1)) or '{{' in CLOZE.sub('', text) or '}}' in CLOZE.sub('', text) or any(not visible_text(m[2]) for m in matches):
                raise ValueError('每条填空须含c1、c2…连续且不重复的非空挖空，不接受提示或嵌套语法')
            if any('::' in m[2] for m in matches): raise ValueError('不接受额外填空提示')
            fields = [html.escape(text, quote=False).replace('\n', '<br>')]
            totals[kind] += len(indices)
        else:
            front = plain(card['front'], 'front'); back = plain(card['back'], 'back')
            if '{{' in front + back or '}}' in front + back:
                raise ValueError('问答卡不可包含模板语法')
            if kind == 'term' and (not re.search(r'[A-Za-z]', front) or re.search(r'[\u3400-\u9fff]', front) or '\n' in front or '<' in front or '>' in front):
                raise ValueError('名词解释正面只能为英文名词，不得有中文提示或HTML')
            checker = AnswerHTML(); checker.feed(back); checker.close()
            if checker.stack or not visible_text(''.join(checker.text)): raise ValueError('答案为空、不可见或HTML未闭合')
            fields = [html.escape(front, quote=False), back]
            totals[kind] += 1
        records.append((kind, ident, fields))
    return source, deck, scope['label'], records, totals


def build(plan, output, replace=False):
    source, name, scope, records, totals = validate(plan)
    output = Path(output)
    if output.suffix.lower() != '.apkg': raise ValueError('只输出.apkg格式')
    if output.exists() and not replace: raise FileExistsError('目标已存在；确认更新同一卡包后才可使用--replace')
    models = {}
    for kind in ('cloze', 'term', 'essay'):
        cloze = kind == 'cloze'
        models[kind] = genanki.Model(stable_id('dcfanki:model:v1:' + kind), 'dcfanki_' + kind + '_v1', fields=[{'name': 'Text'}] if cloze else [{'name': 'Front'}, {'name': 'Back'}], templates=[{'name': 'Card', 'qfmt': '{{cloze:Text}}' if cloze else '{{Front}}', 'afmt': '{{cloze:Text}}' if cloze else '{{FrontSide}}<hr id="answer">{{Back}}'}], css=CSS, model_type=genanki.Model.CLOZE if cloze else genanki.Model.FRONT_BACK)
    decks = {}
    for kind, ident, fields in records:
        if kind not in decks:
            label = {'cloze': '填空', 'term': '名词解释', 'essay': '简答'}[kind]
            decks[kind] = genanki.Deck(stable_id(f'dcfanki:deck:{source}:{scope}:{kind}'), name + '::' + label)
        guid = genanki.guid_for('dcfanki:v1', source, scope, kind, ident)
        decks[kind].add_note(genanki.Note(model=models[kind], fields=fields, tags=[], guid=guid))
    # Stage and verify before atomically replacing an existing output.
    with tempfile.TemporaryDirectory(prefix='dcfanki-build-', dir=output.parent) as temporary:
        folder = Path(temporary); staged = folder / 'deck.apkg'
        genanki.Package(list(decks.values())).write_to_file(str(staged))
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip() is not None: raise ValueError('卡包压缩校验失败')
            db = folder / 'collection.anki2'; db.write_bytes(archive.read('collection.anki2'))
        with closing(sqlite3.connect(db)) as connection:
            if connection.execute('select count(*) from cards').fetchone()[0] != sum(totals.values()): raise ValueError('卡数不匹配')
            if connection.execute('select count(*) from notes').fetchone()[0] != len(records): raise ValueError('笔记数不匹配')
            if connection.execute("select count(*) from notes where trim(tags) != ''").fetchone()[0]: raise ValueError('卡包含多余标签')
            saved_models = json.loads(connection.execute('select models from col').fetchone()[0])
            for mid, fields in connection.execute('select mid,flds from notes'):
                model = saved_models[str(mid)]; values = fields.split('\x1f'); template = model['tmpls'][0]
                if model['type'] == 0:
                    if len(values) != 2 or not values[1].strip() or '{{Back}}' not in template['afmt']: raise ValueError('问答答案字段或背面模板无效')
                elif len(values) != 1 or template['afmt'] != '{{cloze:Text}}':
                    raise ValueError('填空模板包含额外内容')
        if output.exists() and not replace: raise FileExistsError('目标在生成期间已创建，未覆盖')
        staged.replace(output)
    return {'notes': len(records), 'cards': sum(totals.values()), **totals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--replace', action='store_true', help='Replace an existing package after confirming it is the intended update')
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
        print(json.dumps(build(plan, args.output, args.replace), ensure_ascii=False))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
