import argparse
import base64
import html
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image, ImageOps

from interactions import data_uri, img, render_effect


@dataclass(frozen=True)
class Region:
    label: str
    url: str
    box: tuple[int, int, int, int]


def destination(value):
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.netloc == "mp.weixinbridge.com" and parsed.path == "/mp/wapredirect":
        targets = parse_qs(parsed.query).get("url", [])
        if len(targets) != 1:
            raise ValueError("WeChat redirect must contain one destination")
        url = targets[0]
        parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
        raise ValueError("Use a public HTTP(S) URL without embedded credentials")
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise ValueError("Provide the URL by itself")
    return url


def read_regions(rows, width, height):
    if not isinstance(rows, list):
        raise ValueError("Provide an array of regions")
    regions = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each region must define label, url and box")
        box, label, url = row.get("box"), row.get("label"), row.get("url")
        if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("Each box must contain four integer pixel coordinates")
        if not isinstance(label, str) or not label.strip() or not isinstance(url, str):
            raise ValueError("Each region needs a label and URL")
        left, top, right, bottom = box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(f"Box is outside the image or empty: {label}")
        for region in regions:
            x0, y0, x1, y1 = region.box
            if max(left, x0) < min(right, x1) and max(top, y0) < min(bottom, y1):
                raise ValueError(f"Overlapping regions: {label} and {region.label}")
        regions.append(Region(label.strip(), destination(url), tuple(box)))
    return regions


def image_tile(image, box, region=None):
    crop = image.crop(box)
    buffer = BytesIO()
    crop.save(buffer, format="PNG", optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    alt = html.escape(region.label, quote=True) if region else ""
    img = (
        f'<img src="data:image/png;base64,{data}" alt="{alt}" width="{crop.width}" height="{crop.height}" '
        'style="display:block;width:100%;max-width:100%;height:auto;vertical-align:top;border:0;margin:0;padding:0;">'
    )
    if region is None:
        return img
    href = html.escape(region.url, quote=True)
    return (
        f'<a href="{href}" data-linktype="2" style="display:block;line-height:0;margin:0;padding:0;">'
        f"{img}</a>"
    )


def render_poster(image, regions):
    width, height = image.size
    y_edges = sorted({0, height} | {y for region in regions for y in region.box[1::2]})
    bands = []
    for top, bottom in zip(y_edges, y_edges[1:]):
        active = [region for region in regions if region.box[1] <= top < region.box[3]]
        if not active:
            bands.append(image_tile(image, (0, top, width, bottom)))
            continue

        by_span = {(region.box[0], region.box[2]): region for region in active}
        x_edges = sorted({0, width} | {x for span in by_span for x in span})
        cells = []
        for left, right in zip(x_edges, x_edges[1:]):
            tile = image_tile(image, (left, top, right, bottom), by_span.get((left, right)))
            percent = (right - left) * 100 / width
            cells.append(
                f'<section style="display:inline-block;vertical-align:top;width:{percent:.10f}%;margin:0;padding:0;">'
                f"{tile}</section>"
            )
        bands.append(
            '<section style="width:100%;font-size:0;line-height:0;white-space:nowrap;margin:0;padding:0;">'
            + "".join(cells) + "</section>"
        )
    return (
        '<section style="display:block;width:100%;font-size:0;line-height:0;margin:0;padding:0;">'
        + "".join(bands) + "</section>"
    )


def render_image(path, rows):
    with Image.open(path) as source:
        if source.format == "GIF" and getattr(source, "is_animated", False):
            if rows != []:
                raise ValueError("Animated GIFs retain their frames as a whole image. Use a separate static image for hotspots.")
            return img(data_uri("gif", path.read_bytes()))
        oriented = ImageOps.exif_transpose(source)
        mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
        image = oriented.convert(mode)
    return render_poster(image, read_regions(rows, *image.size))


def collect_panels(manifest):
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    panels = data.get("panels") if isinstance(data, dict) else data
    modules = data.get("modules", {}) if isinstance(data, dict) else {}
    if not isinstance(panels, list) or not panels or not isinstance(modules, dict):
        raise ValueError("Provide panels in reading order and an optional map of module names to JSON paths")
    ordered = []
    for panel in panels:
        if not isinstance(panel, dict):
            raise ValueError("Each panel must be a JSON object")
        if "module" not in panel:
            ordered.append((panel, manifest.parent))
            continue
        name = panel["module"]
        if not isinstance(name, str) or not isinstance(modules.get(name), str) or not modules[name]:
            raise ValueError(f"Unknown reusable module: {name}")
        if len(panel) != 1:
            raise ValueError("A module reference must contain only its name")
        module = manifest.parent / modules[name]
        parts = json.loads(module.read_text(encoding="utf-8-sig"))
        if not isinstance(parts, list) or not parts or any(
            not isinstance(part, dict) or "module" in part for part in parts
        ):
            raise ValueError(f"Module {name} must be a nonempty list of image or effect panels")
        ordered.extend((part, module.parent) for part in parts)
    return ordered


def render_stack(manifest):
    posters = []
    for index, (panel, directory) in enumerate(collect_panels(manifest)):
        if "effect" in panel:
            if panel.get("regions"):
                raise ValueError("Configure links in a separate static panel")
            posters.append(render_effect(panel, directory, index))
        else:
            if not isinstance(panel.get("image"), str) or not panel["image"].strip():
                raise ValueError("Each static panel needs an image path")
            path = directory / panel["image"]
            posters.append(render_image(path, panel.get("regions", [])))
    return (
        '<section style="display:block;width:100%;font-size:0;line-height:0;margin:0;padding:0;">'
        + "".join(posters) + "</section>"
    )


def main():
    parser = argparse.ArgumentParser(description="Build a copyable WeChat image or vertical image stack.")
    parser.add_argument("image", type=Path, nargs="?", help="source image in single-image mode")
    parser.add_argument("regions", type=Path, nargs="?", help="region JSON in single-image mode")
    parser.add_argument("output", type=Path, help="destination HTML file")
    parser.add_argument("--stack", type=Path, metavar="MANIFEST", help="JSON list of images in reading order")
    args = parser.parse_args()

    if args.stack is not None and (args.image is not None or args.regions is not None):
        parser.error("Use --stack MANIFEST OUTPUT or IMAGE REGIONS OUTPUT")
    if args.stack is None and (args.image is None or args.regions is None):
        parser.error("Use --stack MANIFEST OUTPUT or IMAGE REGIONS OUTPUT")

    try:
        if args.stack is None:
            rows = json.loads(args.regions.read_text(encoding="utf-8-sig"))
            poster = render_image(args.image, rows)
        else:
            poster = render_stack(args.stack)
        template_path = Path(__file__).resolve().parents[1] / "assets" / "copy.html"
        template = template_path.read_text(encoding="utf-8")
        args.output.write_text(template.replace("__POSTER__", poster), encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
