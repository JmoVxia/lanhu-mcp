from design_structure import parse_design_structure


def _mastergo_text(name, content, size, weight='Regular', color='rgba(34,34,34,1)', left=0, top=0, width=80, height=24):
    return {
        'name': name,
        'type': 'textLayer',
        'visible': True,
        'frame': {'left': left, 'top': top, 'width': width, 'height': height},
        'text': {
            'style': {
                'content': content,
                'font': {'type': weight, 'name': 'Source Han Sans', 'size': size, 'align': 'left'},
            }
        },
        'style': {
            'fills': [{'isEnabled': True, 'color': {'value': color}}],
        },
        'layers': [],
    }


def test_parse_mastergo_popup_fonts_are_logical_points():
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 2},
        'artboard': {
            'name': '新人',
            'type': 'artboard',
            'frame': {'left': 0, 'top': 0, 'width': 750, 'height': 1653},
            'layers': [
                {
                    'name': '组 2731',
                    'type': 'groupLayer',
                    'visible': True,
                    'hasExportImage': False,
                    'frame': {'left': 65, 'top': 424, 'width': 620, 'height': 820},
                    'layers': [
                        _mastergo_text('本周流水', '本周流水', 22, left=147, top=703.5, width=88, height=24, color='rgba(150,155,163,1)'),
                        _mastergo_text('+11.2%', '+11.2%', 20, left=247, top=701, width=69, height=29, color='rgba(254,89,120,1)'),
                        _mastergo_text('45', '45', 26, weight='Medium', left=147, top=740, width=30, height=26),
                    ],
                }
            ],
        },
    }

    parsed = parse_design_structure(sketch)
    texts = {item['text']: item for item in parsed['texts']}

    assert parsed['sliceScale'] == 2
    assert parsed['artboard']['width'] == 375
    assert parsed['artboard']['height'] == 826.5
    assert texts['本周流水']['fontSize'] == 11
    assert texts['本周流水']['fontWeight'] == 400
    assert texts['本周流水']['color'] == 'rgba(150,155,163,1)'
    assert texts['+11.2%']['fontSize'] == 10
    assert texts['45']['fontSize'] == 13
    assert texts['45']['fontWeight'] == 500
    assert texts['本周流水']['x'] == 73.5


def test_parse_issue85_text_style_shape():
    sketch = {
        'meta': {'sliceScale': 2},
        'layers': [
            {
                'name': '标题',
                'type': 'text',
                'visible': True,
                'frame': {'x': 20, 'y': 40, 'width': 80, 'height': 24},
                'textContent': '本月流水',
                'textStyle': {'fontSize': 22, 'fontWeight': 'Regular', 'color': {'value': '#969BA3'}},
            }
        ],
    }

    parsed = parse_design_structure(sketch)
    assert parsed['texts'][0]['text'] == '本月流水'
    assert parsed['texts'][0]['fontSize'] == 11
    assert parsed['texts'][0]['color'] == '#969BA3'


def _mastergo_shape(name, w, h, *, paths=None, fills=None, borders=None,
                    shadows=None, blurs=None, left=0, top=0):
    return {
        'name': name,
        'type': 'shapeLayer',
        'visible': True,
        'clipped': False,
        'frame': {'left': left, 'top': top, 'width': w, 'height': h},
        'radius': [],
        'paths': paths or [],
        'style': {
            'fills': fills or [],
            'borders': borders or [],
            'shadows': shadows or [],
            'blurs': blurs or [],
        },
        'layers': [],
    }


def _rgba01(r, g, b, a=1):
    return {'r': r, 'g': g, 'b': b, 'a': a, 'value': f'rgba({r*255},{g*255},{b*255},{a})'}


def test_mastergo_radius_from_paths_and_pill_cap():
    # 图层级 radius 恒为 []，真实圆角在 paths[].radius
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 2},
        'artboard': {'name': 'a', 'type': 'artboard',
                     'frame': {'left': 0, 'top': 0, 'width': 750, 'height': 100},
                     'layers': [
                         _mastergo_shape('普通圆角', 30, 30, fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(1, 1, 1)}],
                                         paths=[{'type': 'rect', 'radius': {'topLeft': 8, 'topRight': 8, 'bottomLeft': 8, 'bottomRight': 8}}]),
                         _mastergo_shape('胶囊', 10, 10, fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(0, 0, 0)}],
                                         paths=[{'type': 'rect', 'radius': {'topLeft': 1216, 'topRight': 1216, 'bottomLeft': 1216, 'bottomRight': 1216}}]),
                         _mastergo_shape('左圆角', 40, 40, fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(0, 0, 0)}],
                                         paths=[{'type': 'rect', 'radius': {'topLeft': 16, 'topRight': 0, 'bottomLeft': 16, 'bottomRight': 0}}]),
                     ]},
    }
    nodes = {n['name']: n for n in parse_design_structure(sketch)['nodes']}
    assert nodes['普通圆角']['radius'] == 4            # 8 / scale 2
    assert nodes['胶囊']['radius'] == 2.5             # 1216 封顶到 min(w,h)/2 = 5/2 pt
    assert nodes['左圆角']['radius'] == {'topLeft': 8, 'topRight': 0, 'bottomRight': 0, 'bottomLeft': 8}


def test_mastergo_color_border_shadow_blur_gradient():
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 2},
        'artboard': {'name': 'a', 'type': 'artboard',
                     'frame': {'left': 0, 'top': 0, 'width': 750, 'height': 100},
                     'layers': [
                         _mastergo_shape(
                             '卡片', 100, 100,
                             fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(0.09019608, 0.06666667, 0.06666667, 1)}],
                             borders=[{'isEnabled': True, 'width': 2, 'lineAlignment': 'center', 'style': 'solid', 'opacity': 1, 'color': _rgba01(1, 1, 1)}],
                             shadows=[{'isEnabled': True, 'x': 0, 'y': 0, 'blur': 24, 'spread': 0, 'inset': False, 'color': _rgba01(0.13333334, 0.13333334, 0.13333334, 0.05)}],
                             blurs=[{'isEnabled': True, 'radius': 400, 'type': 'Gaussian'}],
                         ),
                         _mastergo_shape(
                             '渐变', 100, 100,
                             fills=[{'isEnabled': True, 'type': 'gradient', 'gradient': {
                                 'type': 0,
                                 'from': {'x': 2.0, 'y': 0.437},
                                 'to': {'x': 1.0, 'y': 0.437},
                                 'stops': [
                                     {'color': _rgba01(0.949, 0.337, 0.451), 'position': 0},
                                     {'color': _rgba01(0.965, 0.643, 0.325), 'position': 1},
                                 ],
                             }}],
                         ),
                     ]},
    }
    nodes = {n['name']: n for n in parse_design_structure(sketch)['nodes']}
    card = nodes['卡片']
    # 颜色由 r/g/b 计算成干净整数，而非脏浮点 value 字符串
    assert card['color'] == 'rgb(23,17,17)'
    assert card['border'] == [{'thickness': 1, 'color': 'rgb(255,255,255)', 'position': 'center'}]
    assert card['shadow'][0]['blur'] == 12 and card['shadow'][0]['color'] == 'rgba(34,34,34,0.05)'
    assert card['blur'] == {'radius': 200, 'type': 'Gaussian'}
    grad = nodes['渐变']['gradient']
    assert grad['type'] == 'linear'
    assert grad['angle'] == 180.0
    assert grad['stops'][0]['color'] == 'rgb(242,86,115)'


def _mastergo_slice(name, w, h, url, left=0, top=0):
    return {
        'name': name, 'type': 'bitmapLayer', 'visible': True, 'clipped': False,
        'frame': {'left': left, 'top': top, 'width': w, 'height': h},
        'radius': [], 'hasExportImage': True,
        'image': {'imageUrl': url, 'size': {'width': w, 'height': h}},
        'layers': [],
    }


def test_slice_inline_and_category():
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 2},
        'artboard': {'name': 'a', 'type': 'artboard',
                     'frame': {'left': 0, 'top': 0, 'width': 750, 'height': 100},
                     'layers': [
                         _mastergo_slice('图标', 48, 48, 'https://cdn/icon.png'),
                         _mastergo_slice('普通图', 200, 200, 'https://cdn/img.png'),
                         _mastergo_slice('背景图', 750, 400, 'https://cdn/bg.png'),
                     ]},
    }
    parsed = parse_design_structure(sketch)
    assert parsed['sliceCount'] == 3
    cats = {s['name']: s['category'] for s in parsed['slices']}
    assert cats == {'图标': 'icon', '普通图': 'img', '背景图': 'bg'}
    assert parsed['slices'][0]['imageUrl'] == 'https://cdn/icon.png'
    assert parsed['slices'][0]['format'] == 'png'


def test_on_demand_max_depth_and_node_path():
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 2},
        'artboard': {'name': 'a', 'type': 'artboard',
                     'frame': {'left': 0, 'top': 0, 'width': 750, 'height': 100},
                     'layers': [{
                         'name': '外层', 'type': 'groupLayer', 'visible': True,
                         'frame': {'left': 0, 'top': 0, 'width': 100, 'height': 100}, 'radius': [],
                         'layers': [{
                             'name': '内层', 'type': 'groupLayer', 'visible': True,
                             'frame': {'left': 10, 'top': 10, 'width': 50, 'height': 50}, 'radius': [],
                             'layers': [_mastergo_shape('里', 20, 20, fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(1, 1, 1)}])],
                         }],
                     }]},
    }
    shallow = parse_design_structure(sketch, max_depth=1)
    top = shallow['nodes'][0]
    assert top.get('truncated') is True and top.get('childCount') == 1 and 'children' not in top

    sub = parse_design_structure(sketch, node_path='外层/内层')
    assert len(sub['nodes']) == 1 and sub['nodes'][0]['name'] == '内层'
    assert sub['nodePath'] == '外层/内层'


def test_gaps_direction_and_folding():
    # 三个等间距横向排列的兄弟 -> direction=row + 单个 gap（折叠）
    def sq(name, left):
        return _mastergo_shape(name, 20, 20, left=left, top=0,
                               fills=[{'isEnabled': True, 'type': 'color', 'color': _rgba01(1, 1, 1)}])
    sketch = {
        'meta': {'host': {'name': 'master'}, 'sliceScale': 1},
        'artboard': {'name': 'a', 'type': 'artboard',
                     'frame': {'left': 0, 'top': 0, 'width': 200, 'height': 40},
                     'layers': [{
                         'name': '行', 'type': 'groupLayer', 'visible': True,
                         'frame': {'left': 0, 'top': 0, 'width': 100, 'height': 20}, 'radius': [],
                         'layers': [sq('a', 0), sq('b', 30), sq('c', 60)],  # 间距均为 10
                     }]},
    }
    row = parse_design_structure(sketch)['nodes'][0]
    assert row['gaps'] == {'direction': 'row', 'gap': 10}
