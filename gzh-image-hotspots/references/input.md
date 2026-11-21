# 运行与参数

整包解压后，保留目录结构。以当前 Skill 目录为工作目录执行以下命令，也可以使用绝对路径。生成器要求 Python 3.9 或更高版本和 Pillow。当前解释器可导入 Pillow 时直接运行；否则在可管理的 Python 环境中使用包内依赖清单。

```text
python -c "import PIL; print(PIL.__version__)"
python -m pip install -r requirements.txt
```

输入 JSON 为 UTF-8。区域坐标基于按 EXIF 旋转后的原图像素，格式为 `[左, 上, 右, 下]`。链接地址填写从分享文案中提取出的完整 HTTP(S) 地址，保留商品参数，去掉与网址无关的引号和尾随空格。脚本会检查坐标越界与重叠。

## 单图

```text
python scripts/build_hotspots.py "海报.jpg" "regions.json" "公众号图片.html"
```

`regions.json` 示例。

```json
[
  {"label":"购买按钮","url":"https://example.com/products?id=123","box":[160,280,520,460]}
]
```

## 竖向长图

```text
python scripts/build_hotspots.py --stack "manifest.json" "公众号长图.html"
```

`manifest.json` 的数组顺序就是从上到下的最终顺序。图片路径可为绝对路径，也可相对该 JSON 所在目录。普通图片可省略 `regions`。每个框以当前图片为坐标原点，区域不随其他图片拼接偏移。

```json
[
  {"image":"01-封面.jpg"},
  {
    "image":"02-商品.jpg",
    "regions":[
      {"label":"购买按钮","url":"https://example.com/products?id=123","box":[160,280,520,460]}
    ]
  },
  {"image":"03-文末.jpg"}
]
```


## 输出检查

- 输出为自包含 HTML，图片已嵌入，交付时只需这个 HTML。携带源图的 HTML 应按源图同等范围分享。
- 用 Chrome 或 Edge 打开，点「一键复制到公众号」，粘贴到正文。编辑器里的确认提示仅表示复制操作成功。等公众号处理图片后保存、重开草稿，再用手机微信点按对应区域。
- 测试时分别确认图是否完整、链接是否随草稿保存，以及手机上是否能打开正确页面。长图要额外确认拼接顺序与接缝。交付方有条件时先实测本地富文本的复制粘贴。
