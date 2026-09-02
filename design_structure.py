"""Parse Lanhu Sketch/Figma/MasterGo JSON into a compact layer tree.

Does not use DDS store_schema_revise, so it still works when
「设计图转代码」is off and schema version data is missing.
Coordinates and font sizes are converted to logical points via sliceScale.
"""
from typing import Optional, Union


_FONT_WEIGHT_NAME_MAP = {
    'thin': 100,
    'ultralight': 200,
    'light': 300,
    'regular': 400,
    'normal': 400,
    'medium': 500,
    'semibold': 600,
    'demibold': 600,
    'bold': 700,
    'heavy': 800,
    'black': 900,
}


def _round_pt(value, scale: float = 1.0):
    if value is None:
        return None
    try:
        number = float(value) / (scale or 1.0)
    except (TypeError, ValueError):
        return None
    rounded = round(number, 1)
    return int(rounded) if rounded == int(rounded) else rounded


def _color_to_css(color) -> Optional[str]:
    if not color:
        return None
    if isinstance(color, str):
        return color
    if not isinstance(color, dict):
        return None
    # 优先用 r/g/b 计算干净的整数值；MasterGo/DDS 的 value 字符串常带浮点脏值
    # （如 rgba(34.00000177323818,...)），对 iOS 不可用。
    r = color.get('r', color.get('red'))
    g = color.get('g', color.get('green'))
    b = color.get('b', color.get('blue'))
    a = color.get('a', color.get('alpha', 1))
    if r is not None and g is not None and b is not None:
        if all(isinstance(item, (int, float)) and abs(item) <= 1 for item in (r, g, b)):
            r, g, b = round(r * 255), round(g * 255), round(b * 255)
        else:
            r, g, b = round(float(r)), round(float(g)), round(float(b))
        try:
            alpha = float(a) if a is not None else 1
        except (TypeError, ValueError):
            alpha = 1
        if alpha < 1:
            return f"rgba({r},{g},{b},{round(alpha, 3)})"
        return f"rgb({r},{g},{b})"
    if color.get('value'):
        return color['value']
    return None


def _first_fill_color(layer: dict) -> Optional[str]:
    fills = []
    style = layer.get('style')
    if isinstance(style, dict):
        fills.extend(style.get('fills') or [])
    fills.extend(layer.get('fills') or [])
    fill_obj = layer.get('fill')
    if isinstance(fill_obj, dict):
        fills.append(fill_obj)
    for fill in fills:
        if not isinstance(fill, dict) or fill.get('isEnabled') is False:
            continue
        css = _color_to_css(fill.get('color'))
        if css:
            return css
    return None


def _apply_alpha(css: Optional[str], alpha: float) -> Optional[str]:
    """Fold a 0-1 alpha into an rgb() css string; leave rgba()/None untouched."""
    if not css or alpha is None or alpha >= 1:
        return css
    if css.startswith('rgb(') and not css.startswith('rgba('):
        inner = css[4:-1]
        return f"rgba({inner},{round(alpha, 2)})"
    return css


def _extract_opacity(layer: dict) -> Optional[float]:
    """Layer opacity as 0-1; None when fully opaque/absent. Handles Figma (0-1) and PSD blendOptions (0-100)."""
    op = layer.get('opacity')
    if op is None:
        blend = layer.get('blendOptions')
        if isinstance(blend, dict):
            raw = blend.get('opacity')
            if isinstance(raw, dict):
                raw = raw.get('value')
            if raw is not None:
                try:
                    raw = float(raw)
                    op = raw / 100 if raw > 1 else raw
                except (TypeError, ValueError):
                    op = None
    if op is None:
        return None
    try:
        op = float(op)
    except (TypeError, ValueError):
        return None
    if op > 1:  # DDS/PSD 用 0-100
        op = op / 100
    if op < 0 or op >= 1:
        return None
    return round(op, 2)


def _extract_border(layer: dict, scale: float):
    """Normalized border list [{thickness, color, position}]; None when absent.

    Handles Figma/MasterGo/DDS `borders` list and PSD `layerEffects.frameFX`.
    """
    borders = []

    raw = []
    style = layer.get('style')
    if isinstance(style, dict):
        raw.extend(style.get('borders') or [])
    raw.extend(layer.get('borders') or [])
    for item in raw:
        if not isinstance(item, dict) or item.get('isEnabled') is False:
            continue
        entry = {}
        # MasterGo 用 width，DDS/Sketch 用 thickness/size
        thickness = item.get('width', item.get('thickness', item.get('size')))
        if thickness is not None:
            entry['thickness'] = _round_pt(thickness, scale)
        color = _color_to_css(item.get('color'))
        opacity = item.get('opacity')
        if color and isinstance(opacity, (int, float)) and opacity < 1:
            color = _apply_alpha(color, opacity)
        if color:
            entry['color'] = color
        # MasterGo 用 lineAlignment(center/inside/outside)，其他用 position
        position = item.get('lineAlignment', item.get('position'))
        if position not in (None, ''):
            entry['position'] = position
        line_style = item.get('style')
        if isinstance(line_style, str) and line_style and line_style.lower() != 'solid':
            entry['style'] = line_style
        if entry:
            borders.append(entry)

    effects = layer.get('layerEffects')
    frame_fx = effects.get('frameFX') if isinstance(effects, dict) else None
    if isinstance(frame_fx, dict) and frame_fx.get('enabled', True):
        entry = {}
        size = frame_fx.get('size')
        if size is not None:
            entry['thickness'] = _round_pt(size, scale)
        color = _color_to_css(frame_fx.get('color'))
        opacity = frame_fx.get('opacity')
        if isinstance(opacity, dict):
            opacity = opacity.get('value')
        if color and opacity is not None:
            try:
                color = _apply_alpha(color, float(opacity) / 100)
            except (TypeError, ValueError):
                pass
        if color:
            entry['color'] = color
        position = {'outsetFrame': 'outside', 'insetFrame': 'inside', 'centeredFrame': 'center'}.get(frame_fx.get('style'))
        if position:
            entry['position'] = position
        if entry:
            borders.append(entry)

    return borders or None


def _extract_radius(layer: dict, scale: float, max_radius: Optional[float] = None):
    """Corner radius in logical points; None when absent.

    Returns a single number when all four corners are equal, otherwise
    {topLeft, topRight, bottomRight, bottomLeft} for iOS maskedCorners.
    `max_radius` (points, usually min(w,h)/2) caps「胶囊/圆形」的超大数值。
    """
    values = None

    # MasterGo: 圆角在矢量 paths 里，paths[].radius = {topLeft,topRight,bottomLeft,bottomRight}
    # 图层级 layer['radius'] 恒为 []，不能用。
    for path in (layer.get('paths') or []):
        if isinstance(path, dict) and isinstance(path.get('radius'), dict):
            corner = path['radius']
            raw = [corner.get('topLeft'), corner.get('topRight'),
                   corner.get('bottomRight'), corner.get('bottomLeft')]
            if any(isinstance(item, (int, float)) and item for item in raw):
                values = [_round_pt(item or 0, scale) for item in raw]
                break

    if values is None:
        radius = layer.get('radius')
        if radius in (None, 0, [], {}):
            style = layer.get('style')
            if isinstance(style, dict):
                radius = style.get('borderRadius') or style.get('radius')
        if radius in (None, 0, [], {}):
            radius = layer.get('cornerRadius')
        if radius in (None, 0, [], {}):
            return None
        if isinstance(radius, (int, float)):
            values = [_round_pt(radius, scale)] * 4
        elif isinstance(radius, (list, tuple)) and radius:
            converted = [_round_pt(item, scale) for item in radius]
            values = (converted + [converted[-1]] * 4)[:4]
        else:
            return radius

    if not values:
        return None

    if isinstance(max_radius, (int, float)) and max_radius > 0:
        values = [min(item, max_radius) if isinstance(item, (int, float)) else item
                  for item in values]

    numeric = [item for item in values if isinstance(item, (int, float))]
    if numeric and not any(numeric):
        return None
    if len(set(values)) == 1:
        return values[0] or None
    return {
        'topLeft': values[0],
        'topRight': values[1],
        'bottomRight': values[2],
        'bottomLeft': values[3],
    }


def _extract_shadow(layer: dict, scale: float):
    """Normalized shadow list [{color, x, y, blur, spread, inset?}]; None when absent."""
    import math
    shadows = []

    raw = list(layer.get('shadows') or [])
    style = layer.get('style')
    if isinstance(style, dict):
        raw.extend(style.get('shadows') or [])
    for item in raw:
        if not isinstance(item, dict) or item.get('isEnabled') is False:
            continue
        entry = {}
        color = _color_to_css(item.get('color'))
        if color:
            entry['color'] = color
        for out_key, keys in (('x', ('offsetX', 'x')), ('y', ('offsetY', 'y')),
                              ('blur', ('blurRadius', 'blur')), ('spread', ('spread', 'choke'))):
            for key in keys:
                if item.get(key) is not None:
                    entry[out_key] = _round_pt(item.get(key), scale)
                    break
        if item.get('type') == 'inner' or item.get('inner') or item.get('inset'):
            entry['inset'] = True
        if entry:
            shadows.append(entry)

    effects = layer.get('layerEffects')
    if isinstance(effects, dict):
        for key, inset in (('dropShadow', False), ('dropShadowMulti', False),
                           ('innerShadow', True), ('innerShadowMulti', True)):
            data = effects.get(key)
            items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            for item in items:
                if not isinstance(item, dict) or not item.get('enabled', True):
                    continue
                entry = {}
                color = _color_to_css(item.get('color'))
                opacity = item.get('opacity')
                if isinstance(opacity, dict):
                    opacity = opacity.get('value')
                if color and opacity is not None:
                    try:
                        color = _apply_alpha(color, float(opacity) / 100)
                    except (TypeError, ValueError):
                        pass
                if color:
                    entry['color'] = color
                distance = item.get('distance', 0) or 0
                angle = item.get('localLightingAngle', {})
                angle = angle.get('value', 120) if isinstance(angle, dict) else (angle or 120)
                rad = math.radians(angle)
                entry['x'] = _round_pt(round(distance * math.cos(rad), 1), scale)
                entry['y'] = _round_pt(round(distance * math.sin(rad), 1), scale)
                if item.get('blur') is not None:
                    entry['blur'] = _round_pt(item.get('blur'), scale)
                if item.get('chokeMatte') is not None:
                    entry['spread'] = _round_pt(item.get('chokeMatte'), scale)
                if inset:
                    entry['inset'] = True
                if entry:
                    shadows.append(entry)

    return shadows or None


_GRADIENT_TYPE_MAP = {0: 'linear', 1: 'radial', 2: 'angular', 3: 'diamond'}


def _extract_gradient(layer: dict):
    """Gradient fill as {type, stops:[{color, position}], from, to, angle}; None when no gradient fill.

    `from`/`to` 为归一化色标手柄坐标，`angle` 为线性渐变方向角（度，屏幕坐标系，+x 向右、+y 向下）。
    """
    import math
    fills = []
    style = layer.get('style')
    if isinstance(style, dict):
        fills.extend(style.get('fills') or [])
    fills.extend(layer.get('fills') or [])
    for fill in fills:
        if not isinstance(fill, dict) or fill.get('isEnabled') is False:
            continue
        is_gradient = fill.get('fillType') == 1 or fill.get('type') in ('gradient', 'Gradient') or fill.get('gradient')
        if not is_gradient:
            continue
        gradient = fill.get('gradient') if isinstance(fill.get('gradient'), dict) else fill
        raw_stops = gradient.get('stops') or gradient.get('colorStops') or gradient.get('colors') or []
        stops = []
        for stop in raw_stops:
            if not isinstance(stop, dict):
                continue
            color = _color_to_css(stop.get('color') or stop)
            entry = {}
            if color:
                entry['color'] = color
            position = stop.get('position', stop.get('location'))
            if isinstance(position, (int, float)):
                pos = float(position)
                if pos > 1:  # 归一化到 0..1（部分来源用 0..100），对应 iOS CAGradientLayer.locations
                    pos = pos / 100
                entry['position'] = round(pos, 3)
            elif position is not None:
                entry['position'] = position
            if entry:
                stops.append(entry)
        out = {}
        gtype = gradient.get('gradientType')
        if gtype is None:
            gtype = gradient.get('type')
        if isinstance(gtype, (int, float)) and int(gtype) in _GRADIENT_TYPE_MAP:
            out['type'] = _GRADIENT_TYPE_MAP[int(gtype)]
        elif isinstance(gtype, str) and gtype not in ('', 'gradient', 'Gradient'):
            out['type'] = gtype
        if stops:
            out['stops'] = stops
        frm, to = gradient.get('from'), gradient.get('to')
        if isinstance(frm, dict) and isinstance(to, dict):
            fx, fy = frm.get('x'), frm.get('y')
            tx, ty = to.get('x'), to.get('y')
            if None not in (fx, fy, tx, ty):
                out['from'] = {'x': round(float(fx), 3), 'y': round(float(fy), 3)}
                out['to'] = {'x': round(float(tx), 3), 'y': round(float(ty), 3)}
                if out.get('type') == 'linear':
                    out['angle'] = round(math.degrees(math.atan2(ty - fy, tx - fx)) % 360, 1)
        if out:
            return out
    return None


def _extract_blur(layer: dict, scale: float):
    """Gaussian/background blur as {type, radius}; None when absent. iOS 毛玻璃/模糊效果。"""
    raw = []
    style = layer.get('style')
    if isinstance(style, dict):
        raw.extend(style.get('blurs') or [])
    raw.extend(layer.get('blurs') or [])
    for item in raw:
        if not isinstance(item, dict) or item.get('isEnabled') is False:
            continue
        radius = item.get('radius', item.get('blur'))
        if radius in (None, 0):
            continue
        entry = {'radius': _round_pt(radius, scale)}
        blur_type = item.get('type')
        if isinstance(blur_type, str) and blur_type:
            entry['type'] = blur_type
        return entry
    return None


def _extract_box_style(layer: dict, scale: float, frame: Optional[dict] = None) -> dict:
    """填充色 / 渐变 / 边框 / 圆角 / 阴影 / 模糊 / 透明度 / 裁剪，容器与形状通用。"""
    out = {}
    fill = _first_fill_color(layer)
    if fill:
        out['color'] = fill
    gradient = _extract_gradient(layer)
    if gradient:
        out['gradient'] = gradient
    border = _extract_border(layer, scale)
    if border:
        out['border'] = border
    max_radius = None
    if isinstance(frame, dict):
        fw, fh = frame.get('width'), frame.get('height')
        if isinstance(fw, (int, float)) and isinstance(fh, (int, float)) and fw and fh:
            max_radius = min(fw, fh) / 2
    radius = _extract_radius(layer, scale, max_radius)
    if radius not in (None, 0):
        out['radius'] = radius
    shadow = _extract_shadow(layer, scale)
    if shadow:
        out['shadow'] = shadow
    blur = _extract_blur(layer, scale)
    if blur:
        out['blur'] = blur
    opacity = _extract_opacity(layer)
    if opacity is not None:
        out['opacity'] = opacity
    # 裁剪：iOS clipsToBounds / masksToBounds
    if layer.get('clipped') is True or layer.get('hasClipMask') is True:
        out['clip'] = True

    # 旋转
    rotation = layer.get('rotation', layer.get('rotate'))
    if isinstance(rotation, (int, float)) and abs(rotation) > 0.01:
        out['rotation'] = round(float(rotation), 1)

    # 混合模式
    blend = layer.get('blendMode')
    if not blend:
        blend_options = layer.get('blendOptions')
        if isinstance(blend_options, dict):
            blend = blend_options.get('mode') or blend_options.get('blendMode')
    if isinstance(blend, str) and blend.strip().lower() not in ('', 'normal', 'passthrough', 'pass-through', 'sourceover'):
        out['blendMode'] = blend

    # 背景图 / 图片填充
    fills = []
    style = layer.get('style')
    if isinstance(style, dict):
        fills.extend(style.get('fills') or [])
    fills.extend(layer.get('fills') or [])
    for fill in fills:
        if not isinstance(fill, dict) or fill.get('isEnabled') is False:
            continue
        image = fill.get('image')
        image_url = image.get('imageUrl') if isinstance(image, dict) else (image if isinstance(image, str) else None)
        image_url = image_url or fill.get('imageUrl')
        if fill.get('fillType') == 2 or fill.get('type') in ('image', 'Image') or image_url:
            if isinstance(image_url, str) and image_url:
                out['backgroundImage'] = image_url
                mode = fill.get('scaleMode') or (image.get('scaleMode') if isinstance(image, dict) else None)
                if isinstance(mode, str) and mode:
                    out['backgroundImageMode'] = mode  # fill/fit/tile/stretch → iOS contentMode
            break

    return out


def _layout_metrics(frame: dict, children: list):
    """Derive inner padding and relative gaps between children from their frames.

    Returns (padding, gaps). padding = {left,top,right,bottom};
    gaps = {direction: row|column, gap} 等间距，或 {direction, gaps:[...]} 不等间距。
    """
    boxes = []
    for child in children:
        cx, cy, cw, ch = child.get('x'), child.get('y'), child.get('width'), child.get('height')
        if None in (cx, cy, cw, ch):
            continue
        boxes.append((cx, cy, cx + cw, cy + ch))
    if not boxes:
        return None, None

    fx, fy, fw, fh = frame.get('x'), frame.get('y'), frame.get('width'), frame.get('height')

    # 排除铺满/超出父容器的背景层、遮罩、误嵌大图：它们不是内容兄弟，会把 padding 压成 0
    # 或算出极端负值（如子在画板 y=0、父在 y=2160 → padding.top=-2160）。仅在还剩内容盒子时排除。
    if None not in (fx, fy, fw, fh) and fw and fh and len(boxes) >= 2:
        parent_area = fw * fh
        content = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) < 0.95 * parent_area]
        if content:
            boxes = content

    padding = None
    if None not in (fx, fy, fw, fh):
        # padding 是派生的「内容内边距」；iOS UIEdgeInsets 不支持负值，子元素溢出父框时截断为 0
        # （真实溢出位置仍由子节点的绝对 x/y 表达）。
        padding = {
            'left': max(0, _round_pt(min(b[0] for b in boxes) - fx, 1) or 0),
            'top': max(0, _round_pt(min(b[1] for b in boxes) - fy, 1) or 0),
            'right': max(0, _round_pt((fx + fw) - max(b[2] for b in boxes), 1) or 0),
            'bottom': max(0, _round_pt((fy + fh) - max(b[3] for b in boxes), 1) or 0),
        }

    gaps = None
    if len(boxes) >= 2:
        spread_x = max(b[2] for b in boxes) - min(b[0] for b in boxes)
        spread_y = max(b[3] for b in boxes) - min(b[1] for b in boxes)
        if spread_x >= spread_y:
            ordered = sorted(boxes, key=lambda b: b[0])
            values = [_round_pt(ordered[i][0] - ordered[i - 1][2], 1) for i in range(1, len(ordered))]
            direction = 'row'
        else:
            ordered = sorted(boxes, key=lambda b: b[1])
            values = [_round_pt(ordered[i][1] - ordered[i - 1][3], 1) for i in range(1, len(ordered))]
            direction = 'column'
        # 仅在非重叠（间距均 ≥0，才是真正的顺序 stack 排列）时才产出 gaps；
        # 重叠/绝对定位不是 stack，输出负 gap 会误导 UIStackView/LinearLayout，此时省略、交给绝对坐标。
        non_overlapping = all(isinstance(v, (int, float)) and v >= 0 for v in values)
        if non_overlapping:
            # 语义化 + 折叠：row/column 对应 iOS UIStackView / Android LinearLayout；等间距压成单个 gap。
            if len(set(values)) == 1:
                gaps = {'direction': direction, 'gap': values[0]}
            else:
                gaps = {'direction': direction, 'gaps': values}
            # 交叉轴对齐（保守：全部子容差内一致才给）。row→start=top/center/end=bottom；column→leading/center/trailing。
            align = _cross_axis_align(boxes, direction)
            if align:
                gaps['align'] = align

    return padding, gaps


def _cross_axis_align(boxes, direction, tol: float = 1.5):
    """交叉轴对齐：row 看 y(top/center/bottom)，column 看 x(leading/center/trailing)。
    仅当所有子在容差内一致时返回 start/center/end，否则 None（不猜）。"""
    if direction == 'row':
        starts = [b[1] for b in boxes]
        ends = [b[3] for b in boxes]
    else:
        starts = [b[0] for b in boxes]
        ends = [b[2] for b in boxes]
    centers = [(s + e) / 2 for s, e in zip(starts, ends)]

    def uniform(vals):
        return len(vals) >= 2 and (max(vals) - min(vals)) <= tol

    if uniform(starts):
        return 'start'
    if uniform(ends):
        return 'end'
    if uniform(centers):
        return 'center'
    return None


def _layer_frame(layer: dict, scale: float) -> dict:
    frame = (
        layer.get('frame')
        or layer.get('realFrame')
        or layer.get('bounds')
        or layer.get('ddsOriginFrame')
        or layer.get('layerOriginFrame')
        or {}
    )
    left = frame.get('left', frame.get('x', layer.get('left', 0))) or 0
    top = frame.get('top', frame.get('y', layer.get('top', 0))) or 0
    width = frame.get('width', layer.get('width', 0)) or 0
    height = frame.get('height', layer.get('height', 0)) or 0
    # 归一化翻转元素的负宽高：负值表示水平/垂直翻转，其原点在另一侧。
    # 规范成标准左上角盒子（否则会输出非法负尺寸、坐标错位并污染 padding/gaps）。
    if isinstance(width, (int, float)) and width < 0:
        left += width
        width = -width
    if isinstance(height, (int, float)) and height < 0:
        top += height
        height = -height
    return {
        'x': _round_pt(left, scale),
        'y': _round_pt(top, scale),
        'width': _round_pt(width, scale),
        'height': _round_pt(height, scale),
    }


def _normalize_font_weight(value) -> Optional[Union[int, str]]:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return int(value)
    mapped = _FONT_WEIGHT_NAME_MAP.get(str(value).lower())
    return mapped if mapped is not None else value


_ALIGN_MAP = {0: 'left', 1: 'right', 2: 'center', 3: 'justify',
              'left': 'left', 'right': 'right', 'center': 'center',
              'centered': 'center', 'justify': 'justify', 'justified': 'justify'}


def _normalize_align(value):
    """统一文本对齐为 left/center/right/justify（对应 iOS NSTextAlignment）。
    MasterGo 给字符串，Sketch justification 给整数码。"""
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return _ALIGN_MAP.get(int(value), value)
    return _ALIGN_MAP.get(str(value).lower(), value)


def _extract_text_props(layer: dict, scale: float) -> dict:
    """MasterGo artboard / Figma textStyle / Sketch textInfo."""
    props = {}

    raw_text = layer.get('text')
    if isinstance(raw_text, dict):
        style = raw_text.get('style') or {}
        font = style.get('font') or raw_text.get('font') or {}
        props['text'] = style.get('content') or raw_text.get('value') or raw_text.get('content') or ''
        if font.get('size') is not None:
            props['fontSize'] = _round_pt(font.get('size'), scale)
        props['fontFamily'] = font.get('name') or font.get('postScriptName')
        props['fontWeight'] = _normalize_font_weight(font.get('fontWeight') or font.get('type'))
        props['align'] = _normalize_align(font.get('align'))
        if font.get('verticalAlignment') not in (None, ''):
            props['verticalAlign'] = font.get('verticalAlignment')  # top/middle/bottom，iOS 竖直对齐
        props['color'] = _color_to_css(style.get('color'))
        # 富文本多段样式：仅取首段，标记以便调用方知道存在逐段差异（完整分段见原始数据）
        runs = raw_text.get('styles')
        if isinstance(runs, list) and len(runs) > 1:
            props['multiStyle'] = True
    elif isinstance(raw_text, str) and raw_text:
        props['text'] = raw_text

    text_style = layer.get('textStyle') or {}
    if text_style:
        props.setdefault('text', layer.get('textContent') or '')
        if text_style.get('fontSize') is not None:
            props['fontSize'] = _round_pt(text_style.get('fontSize'), scale)
        if text_style.get('fontWeight') is not None:
            props['fontWeight'] = _normalize_font_weight(text_style.get('fontWeight'))
        if text_style.get('color'):
            props['color'] = _color_to_css(text_style.get('color'))
        if text_style.get('align'):
            props['align'] = _normalize_align(text_style.get('align'))

    text_info = layer.get('textInfo') or {}
    if text_info:
        if text_info.get('text'):
            props['text'] = text_info.get('text')
        if text_info.get('size') is not None:
            props['fontSize'] = _round_pt(text_info.get('size'), scale)
        props.setdefault('fontFamily', text_info.get('fontPostScriptName') or text_info.get('fontName'))
        if text_info.get('bold') and not props.get('fontWeight'):
            props['fontWeight'] = 700
        if text_info.get('color'):
            props.setdefault('color', _color_to_css(text_info.get('color')))
        if text_info.get('justification') is not None:
            props.setdefault('align', _normalize_align(text_info.get('justification')))

    # 行高 / 字间距 / 斜体（各来源尽力取，逻辑点）
    font = {}
    if isinstance(raw_text, dict):
        font = (raw_text.get('style') or {}).get('font') or raw_text.get('font') or {}
    for src in (font, text_style, text_info):
        if not isinstance(src, dict):
            continue
        if props.get('lineHeight') is None:
            line_height = src.get('lineHeight', src.get('leading'))
            if isinstance(line_height, (int, float)) and line_height not in (None, 0):
                props['lineHeight'] = _round_pt(line_height, scale)
        if props.get('letterSpacing') is None:
            letter_spacing = src.get('letterSpacing', src.get('tracking'))
            if isinstance(letter_spacing, dict):  # MasterGo: {value, unit}
                letter_spacing = letter_spacing.get('value')
            if isinstance(letter_spacing, (int, float)) and letter_spacing != 0:
                props['letterSpacing'] = _round_pt(letter_spacing, scale)
        if not props.get('italic'):
            style_name = src.get('type') if isinstance(src.get('type'), str) else ''
            if src.get('italic') or 'italic' in style_name.lower():
                props['italic'] = True
        if not props.get('underline'):
            underline = src.get('underline')
            if underline not in (None, 0, False, ''):
                props['underline'] = True
        if not props.get('strikethrough'):
            strike = src.get('linethrough', src.get('strikethrough'))
            if strike not in (None, 0, False, ''):
                props['strikethrough'] = True

    if not props.get('color'):
        props['color'] = _first_fill_color(layer)

    # 换行符归一化：\r\n / \r（Windows/PSD/Sketch）统一成 \n，避免 iOS CoreText 排版异常。
    text_val = props.get('text')
    if isinstance(text_val, str) and '\r' in text_val:
        props['text'] = text_val.replace('\r\n', '\n').replace('\r', '\n')

    # 行高 < 字号 时省略：这不是有效的 iOS 行距（会削顶/重叠），多为设计端单行文本的行盒高度，
    # 保留会误导。不虚构数值，直接不输出，交给 iOS 用字体自然行高。
    lh, fs = props.get('lineHeight'), props.get('fontSize')
    if isinstance(lh, (int, float)) and isinstance(fs, (int, float)) and lh < fs:
        props.pop('lineHeight', None)

    return {key: value for key, value in props.items() if value not in (None, '')}


def _slice_asset(layer: dict):
    """解析切图导出图 URL 与格式。兼容：
    Sketch/Figma  -> image.imageUrl / image.svgUrl
    PSD           -> images{png_*: url} / ddsImages{orgUrl}（isSlice 层）"""
    image = layer.get('image')
    if isinstance(image, dict):
        if image.get('imageUrl'):
            return image['imageUrl'], 'png'
        if image.get('svgUrl'):
            return image['svgUrl'], 'svg'
    images = layer.get('images')  # PSD 切图（多倍率），取第一个 http url
    if isinstance(images, dict):
        for key, value in images.items():
            if isinstance(value, str) and value.startswith('http'):
                return value, ('svg' if 'svg' in str(key).lower() else 'png')
    dds = layer.get('ddsImages')  # PSD 原图
    if isinstance(dds, dict):
        url = dds.get('orgUrl') or dds.get('imageUrl')
        if isinstance(url, str) and url.startswith('http'):
            return url, 'png'
    return None, None


def _classify_slice(width, height) -> str:
    """切图按尺寸(逻辑 pt)分类：icon / bg / img。借鉴 starql/lanhu-mcp 的 bg/icon/img 思路，
    阈值按 iOS 逻辑点调整：长边 ≤64pt 视为图标，长边 ≥300pt(接近/超过屏宽)视为背景大图，其余为普通图片。"""
    long_side = max(width or 0, height or 0)
    if long_side and long_side <= 64:
        return 'icon'
    if long_side and long_side >= 300:
        return 'bg'
    return 'img'


def _collect_summaries(nodes: list):
    """单次遍历输出树，汇总 texts / slices / tokens（省一次遍历）。
    texts、slices 以 `id` 作为回指句柄；tokens 按使用频率取 top-N。"""
    from collections import Counter
    texts, slices = [], []
    colors, families, sizes = Counter(), Counter(), Counter()

    def walk(node):
        if not isinstance(node, dict):
            return
        color = node.get('color')
        if isinstance(color, str):
            colors[color] += 1
        node_type = node.get('type')
        if node_type == 'text':
            texts.append({key: node[key] for key in node if key != 'children'})
            family = node.get('fontFamily')
            if family:
                families[family] += 1
            size = node.get('fontSize')
            if size is not None:
                sizes[size] += 1
        elif node_type == 'image' and node.get('imageUrl'):
            slices.append({key: node[key] for key in
                           ('id', 'name', 'imageUrl', 'format', 'category', 'width', 'height', 'x', 'y')
                           if key in node})
        for child in node.get('children') or []:
            walk(child)

    for node in nodes:
        walk(node)

    tokens = {}
    if colors:
        tokens['colors'] = [{'value': v, 'count': c} for v, c in colors.most_common(10)]
    if families:
        tokens['fonts'] = [{'family': v, 'count': c} for v, c in families.most_common(6)]
    if sizes:
        tokens['fontSizes'] = [{'size': v, 'count': c} for v, c in sizes.most_common(8)]
    return texts, slices, (tokens or None)


_MAX_CHILDREN = 80  # 单个容器展示子节点上限，超出只取前 N 个 + 标记，保证超宽扁平分支也能返回（完整树在 savedTo）


def _prune_depth(nodes: list, max_depth: Optional[int], _depth: int = 1) -> list:
    """按 max_depth 截断深度，并对超宽子节点列表按 _MAX_CHILDREN 截断广度。
    被截断的 container 标记 truncated/childCount；被截断的宽列表标记 childrenTruncated/childCount。"""
    out = []
    for node in nodes:
        clone = dict(node)
        children = clone.get('children')
        if children:
            if max_depth and _depth >= max_depth:
                clone['childCount'] = len(children)
                clone['truncated'] = True
                clone.pop('children', None)
            else:
                shown = children
                if len(children) > _MAX_CHILDREN:
                    shown = children[:_MAX_CHILDREN]
                    clone['childCount'] = len(children)
                    clone['childrenTruncated'] = True  # 超宽：只展示前 N 个，其余见 savedTo
                clone['children'] = _prune_depth(shown, max_depth, _depth + 1)
        out.append(clone)
    return out


def _find_subtree(nodes: list, node_id: str) -> Optional[dict]:
    """按稳定 id 精确定位一个节点子树，找不到返回 None（id 唯一，无撞名歧义）。"""
    for node in nodes:
        if node.get('id') == node_id:
            return node
        found = _find_subtree(node.get('children') or [], node_id)
        if found:
            return found
    return None


def parse_design_structure(sketch_data: dict, max_depth: Optional[int] = None,
                           node_id: Optional[str] = None,
                           include: Optional[list] = None) -> dict:
    """
    Build a compact layer tree from raw Lanhu design JSON.

    Returns logical-point frames and font sizes. Nested groups are always
    walked, including groups that also have export images.

    每个节点带稳定唯一 id（原始图层 id），作为定位/回指句柄，避免撞名歧义。
    按需加载（省 token）：
      - max_depth: 只输出到指定层级，更深的 container 标记 truncated+childCount；
        单个容器子节点超 80 个时按广度截断（childrenTruncated+childCount），超宽扁平分支也能返回。
      - node_id: 只输出该 id 起始的子树（配合上一次结果里的 node.id 逐分支展开）。
      - include: 段级白名单，控制是否返回冗余汇总。可选项 'slices'/'texts'/'tokens'
        （'nodes' 恒含）。默认 None=全含；如 ['nodes'] 只回结构树+计数，去掉汇总省 token。
    切图内联：image 节点带 imageUrl/format/category，并在顶层 slices 汇总。
    """
    meta = sketch_data.get('meta') or {}
    slice_scale = float(
        sketch_data.get('sliceScale')
        or sketch_data.get('exportScale')
        or meta.get('sliceScale')
        or 2
    )
    host = (meta.get('host') or {}).get('name') if isinstance(meta.get('host'), dict) else meta.get('host')
    is_figma = host == 'figma'
    _fallback_id = [0]  # 原始图层缺 id 时的稳定兜底序号（同一输入遍历顺序一致，跨调用可复现）

    def _should_skip(layer: dict) -> bool:
        if not layer or not isinstance(layer, dict):
            return True
        if layer.get('visible') is False or layer.get('isVisible') is False:
            return True
        if layer.get('opacity') == 0:
            return True
        name = str(layer.get('name') or '')
        return name.startswith('__lanhu') or name.startswith('_annotation')

    def _process(layer: dict) -> Optional[dict]:
        if _should_skip(layer):
            return None

        name = layer.get('name') or ''
        node_id = layer.get('id')
        if node_id in (None, ''):
            _fallback_id[0] += 1
            node_id = f"n{_fallback_id[0]}"
        else:
            node_id = str(node_id)
        layer_type = (layer.get('type') or layer.get('layerType') or '').strip()
        frame = _layer_frame(layer, slice_scale)
        node = {
            'id': node_id,
            'name': name,
            'type': layer_type or 'unknown',
            **frame,
        }
        if layer.get('isMask') is True:
            node['isMask'] = True  # 裁剪蒙版层，非绘制内容

        children_raw = layer.get('layers') or layer.get('children') or []
        is_group = layer_type in (
            'groupLayer', 'layerSection', 'artboard', 'symbolInstence', 'symbolInstance'
        )
        is_text = layer_type in ('textLayer', 'text') or bool(
            layer.get('textInfo') or layer.get('textStyle') or layer.get('text')
        )

        if is_text and not is_group:
            node['type'] = 'text'
            node.update(_extract_text_props(layer, slice_scale))
            return node

        # 补充：容器/形状统一提取填充色、边框、圆角、阴影、模糊、透明度、裁剪
        # （原本容器有 children 就丢掉了这些）。frame 用于胶囊圆角封顶。
        node.update(_extract_box_style(layer, slice_scale, frame))

        children = []
        for child in children_raw:
            parsed = _process(child)
            if parsed:
                children.append(parsed)
        if children:
            node['type'] = 'container'
            node['children'] = children
            padding, gaps = _layout_metrics(frame, children)
            if padding is not None and any(padding.values()):  # 全 0 无信息量，省略省 token
                node['padding'] = padding
            if gaps is not None:
                node['gaps'] = gaps
            return node

        # 叶子：优先识别导出切图（即使它同时有填充/圆角/边框），避免被当成 shape 而丢掉 imageUrl。
        # slice_url 仅对真正的导出层(layer.image/images/ddsImages)非空；MasterGo 的图片填充(style.fills
        # 里的 ddsImage 单数)不会命中，仍走 backgroundImage，不会误判。
        slice_url, slice_fmt = _slice_asset(layer)
        if slice_url and (not is_figma or layer.get('hasExportImage')):
            node['type'] = 'image'
            node['imageUrl'] = slice_url
            node['format'] = slice_fmt
            node['category'] = _classify_slice(frame.get('width'), frame.get('height'))
            return node

        # 任意可见的盒子样式都说明这是一个需要绘制的形状（含仅渐变/仅阴影等），不能丢
        if any(node.get(key) for key in
               ('color', 'gradient', 'border', 'radius', 'shadow', 'blur', 'backgroundImage')):
            node['type'] = 'shape'
            return node

        if layer.get('hasExportImage'):
            node['type'] = 'image'
            return node

        # 无尺寸无内容的 0×0 冗余层：丢弃以减少视图树噪声（#5）
        if frame.get('width') == 0 and frame.get('height') == 0:
            return None

        if is_group:
            node['type'] = 'container'
            return node
        return None

    root_layers = []
    artboard = sketch_data.get('artboard')
    board = sketch_data.get('board')
    artboard_info = None
    if isinstance(artboard, dict):
        artboard_info = {
            'name': artboard.get('name'),
            **_layer_frame(artboard, slice_scale),
        }
        root_layers = artboard.get('layers') or []
    elif isinstance(board, dict):
        artboard_info = {
            'name': sketch_data.get('psdName') or board.get('name'),
            'x': 0,
            'y': 0,
            'width': _round_pt(board.get('width'), slice_scale),
            'height': _round_pt(board.get('height'), slice_scale),
        }
        root_layers = board.get('layers') or []
    elif sketch_data.get('layers'):
        root_layers = sketch_data['layers']
    elif isinstance(sketch_data.get('info'), list):
        root_layers = sketch_data['info']

    nodes = [node for node in (_process(layer) for layer in root_layers) if node]

    # 汇总先在「完整树」上计算，保证即便返回浅骨架，slices/texts/tokens 仍是全量、
    # sliceCount 不会漏报深层切图（node_id 时按该子树统计）。
    summary_root = nodes
    if node_id:
        subtree = _find_subtree(nodes, node_id)
        summary_root = [subtree] if subtree else []
    out_texts, out_slices, tokens_full = _collect_summaries(summary_root)

    # 再对展示树按需裁剪：先定位子树，再按深度截断
    truncated_root = False
    nodes = summary_root
    if max_depth:
        nodes = _prune_depth(nodes, max_depth)
        truncated_root = True

    # include 段级白名单；仅当含已识别段时才过滤，未识别值不静默丢弃汇总
    known = {'nodes', 'texts', 'slices', 'tokens'}
    active_include = include if (include and any(s in known for s in include)) else None

    def _want(section):
        return active_include is None or section in active_include

    result = {
        'sliceScale': int(slice_scale) if slice_scale == int(slice_scale) else slice_scale,
        'host': host,
        'artboard': artboard_info,
    }
    # texts / slices 是冗余汇总（信息已内联在 nodes 树里）；用 include 可去掉以省 token，但保留计数
    result['textCount'] = len(out_texts)
    if _want('texts'):
        result['texts'] = out_texts
    result['sliceCount'] = len(out_slices)
    if _want('slices'):
        result['slices'] = out_slices
    if _want('tokens') and tokens_full:
        result['tokens'] = tokens_full
    result['nodes'] = nodes
    if node_id:
        result['nodeId'] = node_id
        if not nodes:
            result['note'] = f'未找到 id={node_id} 的节点'
    if max_depth and truncated_root:
        result['maxDepth'] = max_depth
    return result
