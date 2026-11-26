"""Render copyable WeChat interactions without script in the article fragment."""

import base64
import html
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


def source_asset(path):
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image)
        size = normalized.size
        formats = {"JPEG": "jpeg", "PNG": "png", "GIF": "gif"}
        if image.format in formats and (image.format == "GIF" or image.getexif().get(274, 1) == 1):
            return size, data_uri(formats[image.format], path.read_bytes())
        buffer = BytesIO()
        normalized.convert("RGBA").save(buffer, format="PNG")
        return size, data_uri("png", buffer.getvalue())


def data_uri(kind, content):
    return f"data:image/{kind};base64," + base64.b64encode(content).decode("ascii")


def img(src, label=""):
    return (
        f'<img src="{src}" alt="{html.escape(label, quote=True)}" '
        'style="display:block;width:100%;height:auto;margin:0;pointer-events:none;">'
    )


def svg_image(src, width, height, label="", x=0):
    return (
        f'<foreignObject x="{x}" y="0" width="{width:g}" height="{height:g}" pointer-events="none">'
        + img(src, label) + "</foreignObject>"
    )


def svg(body, width, height):
    return (
        '<section style="width:100%;margin:0;padding:0;font-size:0;line-height:0;">'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        'style="width:100%;height:auto;display:block;vertical-align:top;overflow:hidden;-webkit-tap-highlight-color:transparent;">'
        + body + "</svg></section>"
    )


def region_box(box, size, scale):
    if not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box):
        raise ValueError("Provide a hotspot as four integer pixel coordinates")
    left, top, right, bottom = box
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError("The hotspot must be inside the source image")
    return tuple(n * scale for n in (left, top, right-left, bottom-top))


def hit_rect(box, attributes="", pointer_events=True):
    x, y, width, height = box
    return (
        f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" '
        f'fill="transparent"{" pointer-events=\"visible\"" if pointer_events else ""} '
        f'style="cursor:pointer;"{attributes}></rect>'
    )


def fade(assets, width, height, box):
    front, back = (svg_image(uri, width, height) for _, uri in assets)
    return svg(
        back + '<g opacity="1">' + front + hit_rect(box, pointer_events=False)
        + '<animate attributeName="opacity" begin="click" dur="0.42s" values="1;0" '
        'keyTimes="0;1" calcMode="spline" keySplines="0.33 0 0.22 1" fill="freeze" restart="never"></animate>'
        '<set attributeName="pointer-events" to="none" begin="click" fill="freeze"></set></g>',
        width, height,
    )


def swipe(assets):
    slides = "".join(
        '<section data-ignore-width="" style="display:inline-block;vertical-align:top;width:100%;scroll-snap-align:start;">'
        + img(uri) + "</section>"
        for _, uri in assets
    )
    return (
        '<section data-ignore-width="" style="width:100%;overflow-x:auto;overflow-y:hidden;white-space:nowrap;'
        'scroll-snap-type:x mandatory;font-size:0;line-height:0;vertical-align:top;">'
        + slides + "</section>"
    )


def carousel(assets, width, height):
    repeated = [*assets, assets[0]]
    body = "".join(svg_image(uri, width, height, x=i*width) for i, (_, uri) in enumerate(repeated))
    timestamps = [0.0]
    positions = ["0 0"]
    cycle = len(assets) * 3
    for i in range(len(assets)):
        timestamps.extend(((i*3+2.54)/cycle, ((i+1)*3)/cycle))
        positions.extend((f"{-i*width:g} 0", f"{-(i+1)*width:g} 0"))
    keys = ";".join(f"{time:.8f}" for time in timestamps)
    values = ";".join(positions)
    return svg(
        '<g>' + body + f'<animateTransform attributeName="transform" type="translate" '
        f'dur="{cycle}s" keyTimes="{keys}" values="{values}" repeatCount="indefinite"></animateTransform></g>',
        width, height,
    )


def zoom(asset, width, height, box, key):
    _, uri = asset
    cx, cy = box[0]+box[2]/2, box[1]+box[3]/2
    open_id, close_id = key+"Open", key+"Close"
    opening, closing = f"{open_id}.click", f"{close_id}.click"
    transform = (
        f'<g transform="translate({cx:g} {cy:g})"><g>'
        f'<g transform="translate({-cx:g} {-cy:g})">{svg_image(uri,width,height)}</g>'
    )
    for trigger, start, end in ((opening,1,1.55),(closing,1.55,1)):
        transform += (
            f'<animateTransform attributeName="transform" type="scale" begin="{trigger}" '
            f'from="{start}" to="{end}" dur="0.38s" fill="freeze" calcMode="spline" '
            'keyTimes="0;1" keySplines="0.2 0.68 0.25 1"></animateTransform>'
        )
    transform += "</g></g>"
    buttons = ""
    for name, initial, hide, show in (
        (open_id, "visible", opening, closing), (close_id, "hidden", closing, opening)
    ):
        # Animate the parent group's visibility; the rect click bubbles through this group.
        buttons += (
            f'<g visibility="{initial}">' + hit_rect(box, f' id="{name}"')
            + f'<set attributeName="visibility" to="hidden" begin="{hide}" fill="freeze"></set>'
            + f'<set attributeName="visibility" to="visible" begin="{show}" fill="freeze"></set></g>'
        )
    return svg(transform + buttons, width, height)


def animated_gif(paths):
    pictures = []
    for path in paths:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            if image.width > 420:
                image.thumbnail((420, round(420*image.height/image.width)), Image.Resampling.LANCZOS)
            pictures.append(image)
    first, second = pictures
    if first.size != second.size:
        raise ValueError("GIF switch requires images with the same displayed dimensions")
    frames = [first] + [Image.blend(first, second, i/7) for i in range(1, 7)] + [second]
    frames += [Image.blend(second, first, i/7) for i in range(1, 7)]
    durations = [1100] + [60]*6 + [1100] + [60]*6
    buffer = BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0)
    return data_uri("gif", buffer.getvalue())


def render_effect(panel, directory: Path, index):
    effect = panel.get("effect")
    if effect == "gif":
        if isinstance(panel.get("image"), str) and panel["image"]:
            _, uri = source_asset(directory / panel["image"])
            if not uri.startswith("data:image/gif;"):
                raise ValueError("Provide a GIF file or two source images")
            return img(uri)
        paths = panel.get("images")
        if not isinstance(paths, list) or len(paths) != 2 or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError("A GIF switch demo requires two image paths")
        return img(animated_gif([directory / path for path in paths]))

    counts = {"fade": 2, "swipe": None, "carousel": None, "zoom": 1}
    if effect not in counts:
        raise ValueError("Use fade, swipe, carousel, zoom or gif")
    paths = panel.get("images")
    if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
        raise ValueError("Provide image paths in reading order")
    required = counts[effect]
    if (required is not None and len(paths) != required) or (required is None and len(paths) < 2):
        raise ValueError(f"Invalid image count for {effect}")

    assets = [source_asset(directory / path) for path in paths]
    size = assets[0][0]
    if any(original != size for original, _ in assets):
        raise ValueError("Images within one interaction must have the same displayed dimensions")
    if effect == "swipe":
        return swipe(assets)
    # Keep the SVG coordinate space small while the source images retain their resolution.
    scale = min(1, 256/size[0], 384/size[1])
    width, height = (n*scale for n in size)
    if effect == "carousel":
        return carousel(assets, width, height)
    box = region_box(panel.get("box"), size, scale)
    if effect == "zoom":
        return zoom(assets[0], width, height, box, f"gzhZoom{index}")
    return fade(assets, width, height, box)
