# Lanhu MCP

> 面向 AI 编程的蓝湖（Lanhu）设计稿 MCP Server。把设计稿解析成**结构化图层树**，枚举 iOS / Android / Flutter 客户端开发所需的**全部视觉属性与布局关系**，并内置切图清单与按需加载——**不依赖 DDS「设计图转代码」，任何稿子都能稳定读取。**

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-stdio%2Fhttp-6E56CF">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
</p>

## 目录

- [为什么用它](#为什么用它)
- [快速开始](#快速开始)
- [工具一览](#工具一览)
- [`design_structure` 属性参考](#design_structure-属性参考)
- [按需加载与超大设计稿](#按需加载与超大设计稿)
- [架构原则：不依赖 DDS](#架构原则不依赖-dds)
- [隐私与凭据](#隐私与凭据)
- [测试](#测试) · [致谢](#致谢) · [License](#license)

## 为什么用它

- **不依赖 DDS，稳定不失败** — 直接清洗蓝湖原始 Sketch / Figma / MasterGo JSON，设计师未开启「设计图转代码」也照常工作。
- **属性齐全，面向客户端** — 坐标/尺寸/字号统一逻辑点 `pt`，颜色统一干净 `rgb()/rgba()`；覆盖颜色、渐变、边框、逐角圆角、阴影、模糊、透明度、旋转、裁剪、字体全套，直接对应 iOS 属性。
- **父子 + 兄弟布局** — 嵌套 `children` 图层树；容器带 `padding`（子相对父）与 `gaps{direction,gap,align}`（兄弟方向/间距/对齐），直接映射 `UIStackView`/`LinearLayout`，配合绝对坐标完整还原。
- **超省 token，按需加载** — 默认智能渐进：小稿一次到位，大稿返回带唯一 `id` 的浅骨架，再按 `id` 逐分支展开；几百项的超宽列表可 `child_offset` 翻页，**不会因 MCP 输出上限而漏取**。
- **切图不丢** — 图片节点内联下载 `imageUrl`，顶层 `slices[]` 汇总；批量下载与命名交给专用工具。

## 快速开始

**1. 安装**（Python 3.10+）

```bash
git clone https://github.com/JmoVxia/lanhu-mcp.git
cd lanhu-mcp
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

**2. 配置蓝湖 Cookie**

浏览器登录 [lanhuapp.com](https://lanhuapp.com) → `F12` → **Network** → 刷新 → 点任意 `lanhuapp.com` 请求 → **Headers** → 复制请求头里 **`Cookie:`** 的整段值（图文详版见 [GET-COOKIE-TUTORIAL.md](GET-COOKIE-TUTORIAL.md)）。填入 `.env`：

```bash
cp .env.example .env
```
```ini
LANHU_COOKIE=粘贴整段Cookie
```

> Cookie 会过期，失效后按同样方法更新。其余可选项（`DATA_DIR` / `LOG_LEVEL` / `HTTP_TIMEOUT` …）见 `.env.example`。

**3. 接入 MCP 客户端**（Claude Code / Cursor 等，stdio）

`run-stdio.sh` 会自动加载同目录 `.env`，Cookie 放 `.env` 即可；也可直接写进 `env`。

```json
{
  "mcpServers": {
    "lanhu": {
      "command": "/bin/bash",
      "args": ["/绝对路径/lanhu-mcp/run-stdio.sh"],
      "env": { "LANHU_USER_NAME": "yourname", "LANHU_USER_ROLE": "Developer" }
    }
  }
}
```

**4. 使用** — 把设计链接交给 AI：

```
用 lanhu_get_design_structure 解析这个设计稿并生成 iOS 代码：
https://lanhuapp.com/web/#/item/project/detailDetach?pid=xxx&image_id=xxx
```

## 工具一览

| 工具 | 说明 |
| --- | --- |
| **`lanhu_get_design_structure`** | ⭐ 主力：结构化图层树，枚举全部客户端属性 + 切图内联 + 智能按需加载 |
| `lanhu_get_design_slices` | 批量下载切图资源，自动分类命名 |
| `lanhu_get_designs` | 获取项目下的设计图列表 |
| `lanhu_get_ai_analyze_design_result` | 生成 HTML+CSS（可选/遗留，走 DDS，属性以 `design_structure` 为准） |
| `lanhu_get_ai_analyze_page_result` · `lanhu_get_pages` · `lanhu_list_product_documents` | 原型 / Axure / 需求文档（PRD） |
| `lanhu_resolve_invite_link` · `lanhu_get_members` | 解析邀请链接 · 项目成员 |
| `lanhu_say*` | 团队留言 / 协作评论 |

## `design_structure` 属性参考

坐标 / 尺寸 / 字号均为逻辑点 `pt`，颜色为干净 `rgb()/rgba()`。每个节点带稳定唯一 `id`（定位句柄）、`name`、`type`（`container`/`text`/`shape`/`image`）。

| 分组 | 字段 |
| --- | --- |
| **布局** | `x, y, width, height`（画板绝对坐标）；容器 `padding{left,top,right,bottom}`（子相对父）、`gaps{direction:row\|column, gap 或 gaps[], align}`（兄弟方向/间距/交叉轴对齐） |
| **外观** | `color` · `gradient{type,stops,from,to,angle}` · `border[{thickness,color,position,style}]` · `radius`（数值或逐角 `{topLeft,topRight,bottomRight,bottomLeft}`）· `shadow[{color,x,y,blur,spread,inset}]` · `blur{type,radius}` · `opacity` · `rotation` · `blendMode` · `clip` · `backgroundImage` / `backgroundImageMode` |
| **文本** | `text, fontSize, fontFamily, fontWeight, color, align, verticalAlign, lineHeight, letterSpacing, italic, underline, strikethrough, multiStyle` |
| **切图** | `image` 节点内联 `imageUrl / format(png\|svg) / category(icon\|bg\|img)`；顶层 `slices[]` 汇总 |
| **主题** | 顶层 `tokens{colors,fonts,fontSizes}`（按使用频率 top-N，便于建 `UIColor` 调色板 / 字体表） |

示例（片段）：

```jsonc
{
  "id": "2:1042", "name": "标题栏", "type": "container",
  "x": 0, "y": 44, "width": 375, "height": 44,
  "color": "rgb(255,255,255)",
  "padding": { "left": 16, "top": 12, "right": 16, "bottom": 12 },
  "gaps": { "direction": "row", "gap": 8, "align": "center" },
  "children": [
    { "id": "2:1043", "name": "返回", "type": "image",
      "imageUrl": "https://.../back.png", "format": "png", "category": "icon",
      "x": 16, "y": 54, "width": 24, "height": 24 },
    { "id": "2:1044", "name": "页面标题", "type": "text", "text": "我的",
      "fontSize": 17, "fontWeight": 500, "color": "rgb(34,34,34)", "align": "center" }
  ]
}
```

**iOS 映射**：`color→backgroundColor` · `radius→layer.cornerRadius`（逐角用 `maskedCorners`）· `border→layer.borderWidth/borderColor` · `shadow→layer.shadow*` · `blur→UIVisualEffectView` · `opacity→alpha` · `clip→clipsToBounds` · `gradient→CAGradientLayer`（用 `angle/from/to` 定方向）· `gaps→UIStackView(axis/spacing/alignment)`。

## 按需加载与超大设计稿

> 目标：**用最少的 token 精确读取，且再大的稿也不会因 MCP 输出上限而漏取。**

`lanhu_get_design_structure` 的参数：

| 参数 | 作用 |
| --- | --- |
| *（默认，无参）* | 智能渐进：小稿一次全量；中大稿自动返回「能放进 token 预算的最大深度骨架」，被截断的容器标记 `truncated` + `childCount` |
| `node_id` | 展开某节点子树（`id` 取自上一次结果的 `node.id`），唯一无撞名歧义——渐进的下一步 |
| `child_offset` | 配合 `node_id` **翻页超宽列表**（>80 直接子节点）：结果里 `nextChildOffset` 给出下一页起点，几百项也能逐页取全 |
| `max_depth` | 显式只输出到第 N 层 |
| `include` | 段级白名单（`nodes`/`texts`/`slices`/`tokens`），如 `['nodes']` 只回结构树省 token |

机制：**完整树始终解析并写盘（`savedTo`），返回体只给当前所需**。同一版本重复读取/逐分支展开走进程内缓存（`json_url` 版本键），跳过重复下载与解析；版本变化自动失效。

典型流程：

```
默认调用 → 浅骨架（每节点带 id，truncated 容器带 childCount）
  → node_id=<目标容器 id> 展开该分支
    → 若是超宽列表：child_offset=0 / nextChildOffset 逐页翻
```

## 架构原则：不依赖 DDS

这是**架构级约束**，不是可选项：

- **为什么** — 大量蓝湖稿未开启「设计图转代码」（DDS `store_schema_revise`）。以 DDS 为主链路的方案遇到这类稿会失败或残缺。
- **怎么做** — 核心链路一律走 `/api/project/image` 的原始设计 JSON，由 `design_structure.py` 清洗成图层树。`lanhu_get_design_structure` / `lanhu_get_design_slices` **全程零 DDS**。
- **边界** — 仅 `lanhu_get_ai_analyze_design_result`（生成 HTML，可选/遗留）会尝试 DDS，且不可用时**自动降级**为原始 JSON 的 sketch-HTML，不硬依赖。

## 隐私与凭据

- **不自动登录、不采集账号信息。** 服务只用你手动配置的 `LANHU_COOKIE`，以你的身份调用蓝湖官方接口。
- Cookie 仅存本地 `.env`（已被 `.gitignore` 忽略，不进版本库）；`data/`、`logs/` 同样忽略。
- 内置 Playwright 仅用于跟随蓝湖前端跳转（邀请/detail 链接），复用你提供的 Cookie，不做任何凭据抓取。

## 测试

```bash
./venv/bin/python -m pytest tests/ -q
```

## 致谢

- 基于 [dsphper/lanhu-mcp](https://github.com/dsphper/lanhu-mcp)（MIT）二次开发。
- 图层树 / 切图分类思路参考 [starql/lanhu-mcp](https://github.com/starql/lanhu-mcp)；稳定 `node_id` 寻址、按需加载参考 [Framelink Figma MCP](https://github.com/GLips/Figma-Context-MCP)。

## License

[MIT](LICENSE) · Copyright (c) 2025 Lanhu MCP Server Contributors · Copyright (c) 2026 JmoVxia
