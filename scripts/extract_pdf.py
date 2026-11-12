"""Extract text/style candidates only from explicitly selected PDF pages."""
import argparse
import json
import math
import re
from pathlib import Path

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar, LTCurve
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage


class StyleDevice(PDFPageAggregator):
    def render_string(self, textstate, seq, ncs, graphicstate):
        self.text_render_mode = textstate.render
        return super().render_string(textstate, seq, ncs, graphicstate)

    def render_char(self, *args):
        advance = super().render_char(*args)
        self.cur_item._objs[-1].text_render_mode = self.text_render_mode
        return advance


def walk(item):
    if isinstance(item, (LTChar, LTCurve)):
        yield item
    elif hasattr(item, '_objs'):
        for child in item._objs:
            yield from walk(child)


def parse_pages(value):
    pages = set()
    for token in value.split(','):
        token = token.strip()
        if not re.fullmatch(r'[1-9]\d*(?:-[1-9]\d*)?', token):
            raise ValueError('页码必须为1起算的PDF页序号，例如 8-14,17')
        ends = list(map(int, token.split('-')))
        start, end = ends[0], ends[-1]
        if end < start or end - start > 10000:
            raise ValueError('页码范围倒置或过大')
        pages.update(range(start, end + 1))
    return sorted(pages)


def color_name(color):
    if isinstance(color, (float, int)):
        rgb = (color,) * 3
    elif isinstance(color, (tuple, list)) and len(color) == 3:
        rgb = color
    elif isinstance(color, (tuple, list)) and len(color) == 4:
        cyan, magenta, yellow, black = color
        rgb = tuple(1 - min(1, v + black) for v in (cyan, magenta, yellow))
    else:
        return 'other'
    if not all(isinstance(v, (int, float)) for v in rgb):
        return 'other'
    red, green, blue = rgb
    if max(rgb) < .15:
        return 'black'
    if red > .55 and red > 1.5 * green and red > 1.5 * blue:
        return 'red'
    if blue > .4 and blue > 1.5 * red and blue > green:
        return 'blue'
    return 'other'


def extract(source, pages, first_top=0, last_bottom=None):
    if not pages or pages != sorted(set(pages)) or any(type(n) is not int or n < 1 for n in pages):
        raise ValueError('必须提供排序且不重复的正整数页码')
    if not math.isfinite(first_top) or first_top < 0 or (last_bottom is not None and (not math.isfinite(last_bottom) or last_bottom <= 0)):
        raise ValueError('裁剪坐标必须是有效的非负PDF点数')
    manager = PDFResourceManager(); device = StyleDevice(manager)
    interpreter = PDFPageInterpreter(manager, device)
    results = []
    with Path(source).open('rb') as handle:
        for number, pdfpage in zip(pages, PDFPage.get_pages(handle, pagenos={n - 1 for n in pages}, check_extractable=True)):
            interpreter.process_page(pdfpage)
            layout = device.get_result()
            top = first_top if number == pages[0] else 0
            bottom = last_bottom if number == pages[-1] and last_bottom is not None else layout.height
            if not 0 <= top < bottom <= layout.height:
                raise ValueError(f'第{number}页裁剪边界不在页面内')
            objects = list(walk(layout)); chars = []
            for item in objects:
                if not isinstance(item, LTChar) or abs(item.matrix[1]) > .01 or abs(item.matrix[2]) > .01:
                    continue
                y = layout.height - item.y1
                if not top <= y < bottom:
                    continue
                color = color_name(item.graphicstate.ncolor)
                bold = item.text_render_mode in (1, 2) or bool(re.search(r'bold|simhei|heiti|黑体', str(item.fontname), re.I))
                kind = color if color in ('red', 'blue') else 'black_bold' if color == 'black' and bold else 'plain'
                chars.append({'text': item.get_text(), 'x': item.x0, 'x1': item.x1, 'y': y, 'bottom': layout.height - item.y0, 'baseline': layout.height - item.matrix[5], 'kind': kind})
            if len(''.join(c['text'].strip() for c in chars)) < 5:
                raise ValueError(f'第{number}页选定区域无可用文本；请回查扫描页、裁剪范围或字体编码，不可当成转换成功')
            rows = []
            for char in sorted(chars, key=lambda c: (c['baseline'], c['x'])):
                row = next((r for r in rows if abs(r[0] - char['baseline']) < 2), None)
                if row is None:
                    rows.append([char['baseline'], [char]])
                else:
                    row[1].append(char)
            lines = []; serial = 0
            for baseline, letters in sorted(rows):
                runs = []
                for char in sorted(letters, key=lambda c: c['x']):
                    if not runs or char['kind'] != runs[-1]['kind'] or char['x'] - runs[-1]['x1'] > 6:
                        runs.append(dict(char))
                    else:
                        run = runs[-1]; run['text'] += char['text']; run['x1'] = char['x1']
                        run['y'] = min(run['y'], char['y']); run['bottom'] = max(run['bottom'], char['bottom'])
                spans = []
                for run in runs:
                    if run['kind'] == 'plain' or not run['text'].strip():
                        continue
                    serial += 1
                    underlined = any(isinstance(obj, LTCurve) and (color_name(obj.stroking_color) == run['kind'] or color_name(obj.non_stroking_color) == run['kind']) and obj.height <= 3 and obj.width >= (run['x1'] - run['x']) * .65 and abs(layout.height - obj.y0 - baseline) <= 5 and obj.x0 <= run['x'] + 3 and obj.x1 >= run['x1'] - 3 for obj in objects)
                    spans.append({'id': f'p{number}-s{serial}', 'kind': run['kind'], 'text': run['text'].strip(), 'bounds': [round(run[k], 2) for k in ('x', 'y', 'x1', 'bottom')], 'underlined': underlined})
                lines.append({'y': round(baseline, 2), 'text': ' '.join(r['text'].strip() for r in runs if r['text'].strip()), 'spans': spans})
            results.append({'page': number, 'width': layout.width, 'height': layout.height, 'lines': lines})
    if len(results) != len(pages):
        raise ValueError('至少一个请求页码超出PDF总页数')
    return {'source': Path(source).name, 'pages': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--pages', required=True, help='1-based PDF page numbers, e.g. 8-14,17')
    parser.add_argument('--first-top', type=float, default=0, help='First page top boundary in PDF points from page top')
    parser.add_argument('--last-bottom', type=float, help='Last page bottom boundary in PDF points from page top')
    parser.add_argument('--output', required=True, type=Path, help='Temporary candidates JSON, not a final deliverable')
    args = parser.parse_args()
    try:
        if args.output.resolve() == args.pdf.resolve():
            raise ValueError('输出路径不能指向原PDF')
        result = extract(args.pdf, parse_pages(args.pages), args.first_top, args.last_bottom)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(f'已提取{len(result["pages"])}个指定页面；候选内容仍需对照原页确认。')
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
