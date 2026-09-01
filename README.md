# Lanhu MCP

一个用于蓝湖（Lanhu）设计稿的 MCP Server：把设计稿解析成**结构化图层树**，枚举 iOS / Android / Flutter 等客户端开发所需的**全部视觉属性**，并支持切图下载、需求文档、评论协作等能力。

> 核心思路：直接读取蓝湖原始设计 JSON，**不依赖 DDS「设计图转代码」**。即使设计师没有开启「设计图转代码」，也能稳定拿到完整、精确的属性。

## ✨ 特性

- **不依赖 DDS，稳定不失败**：`lanhu_get_design_structure` 直接清洗原始 Sketch / Figma / MasterGo JSON，DDS `store_schema_revise` 失败也不影响。
- **属性齐全（面向客户端）**：坐标 / 尺寸 / 字号统一为逻辑点 `pt`，颜色为干净的 `rgb()/rgba()`。枚举 颜色、渐变（含方向 angle）、边框、逐角圆角、阴影（含内阴影）、模糊、透明度、旋转、裁剪、字体全套。
- **层次结构 + 相对关系**：嵌套 `children` 图层树；容器带 `padding`（子相对父）与 `gaps`（兄弟间距），配合绝对坐标 `x/y` 完整还原布局。
- **切图内联**：图片节点直接带下载 `imageUrl` 与分类（`icon` / `bg` / `img`），顶层 `slices[]` 汇总，一次拿全，无需再走 DDS。
- **按需加载省 token**：`max_depth` 先拉骨架，`node_path` 再逐分支展开，避免一次吐出整棵大树。

## 🧰 工具一览

| 工具 | 说明 |
| --- | --- |
| `lanhu_get_design_structure` | ⭐ 结构化图层树，枚举全部客户端属性 + 切图内联 + 按需加载（**主力**） |
| `lanhu_get_design_slices` | 批量下载设计稿切图资源，自动分类命名 |
| `lanhu_get_designs` | 获取项目下的设计图列表 |
| `lanhu_get_ai_analyze_design_result` | 走 DDS 生成 HTML+CSS（可选，属性以 `design_structure` 叠加为准） |
| `lanhu_get_ai_analyze_page_result` | 分析 Axure / 原型页面 |
| `lanhu_get_pages` | 获取原型 / 需求页面 |
| `lanhu_list_product_documents` | 列出产品需求文档（PRD） |
| `lanhu_resolve_invite_link` | 解析蓝湖邀请链接，提取项目参数 |
| `lanhu_get_members` | 获取项目成员 |
| `lanhu_say` / `lanhu_say_list` / `lanhu_say_detail` / `lanhu_say_edit` / `lanhu_say_delete` | 团队留言 / 协作评论 |

## 🚀 安装

需要 Python **3.10+**。

```bash
git clone https://github.com/JmoVxia/lanhu-mcp.git
cd lanhu-mcp
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 🔑 配置

复制 `.env.example` 为 `.env`，至少填入蓝湖 Cookie：

```bash
cp .env.example .env
```

```ini
LANHU_COOKIE=你的蓝湖Cookie
```

获取 Cookie 的详细步骤见 [GET-COOKIE-TUTORIAL.md](GET-COOKIE-TUTORIAL.md)。其余可选项（`DATA_DIR` / `LOG_LEVEL` / `HTTP_TIMEOUT` 等）见 `.env.example`。

> `.env`、`data/`、`logs/` 已被 `.gitignore` 忽略，Cookie 等私密信息不会进入版本库。

## 🔌 接入 MCP 客户端

以 stdio 方式接入（Claude Code / Cursor 等）：

```json
{
  "mcpServers": {
    "lanhu": {
      "command": "/bin/bash",
      "args": ["/绝对路径/lanhu-mcp/run-stdio.sh"],
      "env": {
        "LANHU_USER_NAME": "yourname",
        "LANHU_USER_ROLE": "Developer"
      }
    }
  }
}
```

## 💡 使用示例

直接把蓝湖设计链接交给 AI，让它调用 `lanhu_get_design_structure`：

```
用 lanhu_get_design_structure 解析这个设计稿，按返回的属性生成 iOS 代码：
https://lanhuapp.com/web/#/item/project/detailDetach?pid=xxx&image_id=xxx
```

大图先看骨架，再深入某个分支（省 token）：

```
先 max_depth=2 看整体结构；
再对某个容器传 node_path="外层容器/内层" 展开细节。
```

## 🎯 design_structure 返回的属性

坐标 / 尺寸 / 字号均为逻辑点 `pt`，颜色为干净的 `rgb()/rgba()`。

- **布局**：`x, y, width, height`（画板绝对坐标）；容器附 `padding{left,top,right,bottom}` 与 `gaps{axis,values}`（相对关系）
- **外观**：`color` · `gradient{type,stops,from,to,angle}` · `border[{thickness,color,position,style}]` · `radius`（数值或 `{topLeft,topRight,bottomRight,bottomLeft}`）· `shadow[{color,x,y,blur,spread,inset}]` · `blur{type,radius}` · `opacity` · `rotation` · `blendMode` · `clip` · `backgroundImage`
- **文本**：`text, fontSize, fontFamily, fontWeight, color, align, lineHeight, letterSpacing, italic, underline, strikethrough`
- **切图**：`image` 节点内联 `imageUrl / format / category`；顶层 `slices[]` 汇总

iOS 映射参考：`color→backgroundColor`、`radius→layer.cornerRadius`（逐角用 `maskedCorners`）、`border→layer.borderWidth/borderColor`、`shadow→layer.shadow*`、`blur→UIVisualEffectView`、`opacity→alpha`、`clip→clipsToBounds`、`gradient→CAGradientLayer`（用 `angle/from/to` 定方向）。

## 🧪 测试

```bash
./venv/bin/python -m pytest tests/ -q
```

## 🙏 致谢

- 基于 [dsphper/lanhu-mcp](https://github.com/dsphper/lanhu-mcp)（MIT）二次开发。
- 结构化图层树 / 切图分类思路参考了 [starql/lanhu-mcp](https://github.com/starql/lanhu-mcp)。

## 📄 License

[MIT](LICENSE)
