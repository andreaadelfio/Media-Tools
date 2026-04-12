from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, PngImagePlugin, UnidentifiedImageError


PARAMETER_MIN = 0.0
PARAMETER_MAX = 1.5
TEST_CROP_SIZE_RATIO = 0.2


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def probe_values(low: float, high: float, margin: float) -> list[float]:
    margin = clamp(margin, 0.0, (high - low) / 2.0)
    values = [round(low + margin, 2), round(high - margin, 2)]
    return [values[0]] if values[0] == values[1] else values


def load_source_metadata(source: Path) -> dict:
    try:
        with Image.open(source) as pil_image:
            return {
                "exif": pil_image.info.get("exif"),
                "icc_profile": pil_image.info.get("icc_profile"),
                "dpi": pil_image.info.get("dpi"),
                "xmp": pil_image.info.get("xmp") or pil_image.info.get("XML:com.adobe.xmp"),
                "comment": pil_image.info.get("comment"),
                "png_text": dict(getattr(pil_image, "text", {})),
            }
    except (UnidentifiedImageError, OSError):
        return {}


def save_image_with_metadata(image: np.ndarray, destination: Path, metadata: dict) -> None:
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    extension = destination.suffix.lower()
    save_kwargs: dict = {}

    if extension in {".jpg", ".jpeg"}:
        save_kwargs["quality"] = 95
    if metadata.get("dpi"):
        save_kwargs["dpi"] = metadata["dpi"]
    if extension in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
        if metadata.get("exif"):
            save_kwargs["exif"] = metadata["exif"]
        if metadata.get("icc_profile"):
            save_kwargs["icc_profile"] = metadata["icc_profile"]
    if extension in {".jpg", ".jpeg", ".tif", ".tiff", ".webp"} and metadata.get("xmp"):
        save_kwargs["xmp"] = metadata["xmp"]
    if extension in {".jpg", ".jpeg"} and metadata.get("comment"):
        save_kwargs["comment"] = metadata["comment"]
    if extension == ".png" and metadata.get("png_text"):
        pnginfo = PngImagePlugin.PngInfo()
        for key, value in metadata["png_text"].items():
            pnginfo.add_text(key, str(value))
        save_kwargs["pnginfo"] = pnginfo

    try:
        pil_image.save(destination, **save_kwargs)
    except (TypeError, ValueError, OSError):
        pil_image.save(destination)


def reduce_digital_noise(image: np.ndarray, denoise: float) -> np.ndarray:
    denoise = clamp(denoise, PARAMETER_MIN, PARAMETER_MAX)
    if denoise <= 0.0:
        return image

    image_u8 = np.clip(image * 255.0, 0.0, 255.0).astype(np.uint8)
    denoised = cv2.fastNlMeansDenoisingColored(
        image_u8,
        None,
        h=int(round(4 + denoise * 8)),
        hColor=int(round(4 + denoise * 6)),
        templateWindowSize=7,
        searchWindowSize=21 if denoise >= 0.8 else 15,
    ).astype(np.float32) / 255.0

    ycrcb = cv2.cvtColor((denoised * 255.0).astype(np.uint8), cv2.COLOR_BGR2YCrCb)
    chroma_blur = 1.0 + 1.5 * denoise
    ycrcb[..., 1] = cv2.GaussianBlur(ycrcb[..., 1], (0, 0), sigmaX=chroma_blur, sigmaY=chroma_blur)
    ycrcb[..., 2] = cv2.GaussianBlur(ycrcb[..., 2], (0, 0), sigmaX=chroma_blur, sigmaY=chroma_blur)
    cleaned = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR).astype(np.float32) / 255.0

    luminance = 0.114 * image[..., 0] + 0.587 * image[..., 1] + 0.299 * image[..., 2]
    shadow_mask = np.clip((0.7 - luminance) / 0.7, 0.0, 1.0) ** 1.4
    blend = (0.45 + 0.35 * denoise) * shadow_mask[..., None]
    return np.clip(image * (1.0 - blend) + cleaned * blend, 0.0, 1.0)


def sharpen_edges(image: np.ndarray, sharpen: float) -> np.ndarray:
    sharpen = clamp(sharpen, PARAMETER_MIN, PARAMETER_MAX)
    if sharpen <= 0.0:
        return image
    gray = cv2.cvtColor((image * 255.0).astype(np.uint8), cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    edge_mask = np.clip((magnitude - 10.0) / 50.0, 0.0, 1.0) ** 0.9
    edge_mask = cv2.GaussianBlur(edge_mask, (0, 0), sigmaX=1.0, sigmaY=1.0)
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.1, sigmaY=1.1)
    detail = image - blurred
    amount = 0.35 + 0.55 * sharpen
    return np.clip(image + detail * amount * edge_mask[..., None], 0.0, 1.0)


def build_denoised_base(image: np.ndarray, denoise: float) -> np.ndarray:
    working = image.astype(np.float32) / 255.0
    return reduce_digital_noise(working, denoise)


def render_processed_image(denoised_base: np.ndarray, sharpen: float) -> np.ndarray:
    working = sharpen_edges(denoised_base, sharpen)
    return np.clip(working * 255.0, 0.0, 255.0).astype(np.uint8)


def find_sharp_crop_centers(image: np.ndarray, crop_count: int = 1) -> list[tuple[int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    height, width = gray.shape
    window = max(24, int(min(height, width) * TEST_CROP_SIZE_RATIO))
    if window % 2 == 1:
        window += 1
    score_map = cv2.GaussianBlur(magnitude, (0, 0), sigmaX=max(4.0, window / 6.0), sigmaY=max(4.0, window / 6.0))
    centers: list[tuple[int, int]] = []
    suppression_radius = max(20, window // 2)
    working = score_map.copy()

    for _ in range(crop_count):
        _, max_val, _, max_loc = cv2.minMaxLoc(working)
        if max_val <= 0:
            break
        x, y = max_loc
        centers.append((x, y))
        x1 = max(0, x - suppression_radius)
        y1 = max(0, y - suppression_radius)
        x2 = min(width, x + suppression_radius)
        y2 = min(height, y + suppression_radius)
        working[y1:y2, x1:x2] = 0

    return centers or [(width // 2, height // 2)]


def save_test_crops(image: np.ndarray, destination_dir: Path, stem: str, suffix: str, metadata: dict) -> list[Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    height, width = image.shape[:2]
    crop_size = max(64, int(min(height, width) * TEST_CROP_SIZE_RATIO))
    crop_size = min(crop_size, height, width)
    half = crop_size // 2
    saved: list[Path] = []

    for index, (center_x, center_y) in enumerate(find_sharp_crop_centers(image), start=1):
        x1 = max(0, min(width - crop_size, center_x - half))
        y1 = max(0, min(height - crop_size, center_y - half))
        crop = image[y1:y1 + crop_size, x1:x1 + crop_size]
        path = destination_dir / f"crop_{index}_{stem}{suffix}"
        save_image_with_metadata(crop, path, metadata)
        saved.append(path)
    return saved


def process_photo(source: Path, output_dir: Path, denoise: float, sharpen: float, test_crops: bool) -> dict:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Impossibile leggere l'immagine: {source}")
    metadata = load_source_metadata(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{source.stem}_final{source.suffix.lower()}"

    denoised_base = build_denoised_base(image, denoise)
    rendered = render_processed_image(denoised_base, sharpen)
    save_image_with_metadata(rendered, destination, metadata)

    crop_paths: list[str] = []
    if test_crops:
        crop_dir = output_dir / f"{destination.stem}_test"
        for crop in save_test_crops(rendered, crop_dir, destination.stem, source.suffix.lower(), metadata):
            crop_paths.append(str(crop))

    return {
        "mode": "definitive",
        "input": str(source),
        "output": str(destination),
        "denoise": denoise,
        "sharpen": sharpen,
        "test_crops": crop_paths,
    }


def process_photo_test(source: Path, output_dir: Path, probe_margin: float, test_crops: bool) -> dict:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Impossibile leggere l'immagine: {source}")
    metadata = load_source_metadata(source)
    output_dir.mkdir(parents=True, exist_ok=True)

    original_copy = output_dir / f"original{source.suffix.lower()}"
    save_image_with_metadata(image, original_copy, metadata)

    denoise_values = probe_values(PARAMETER_MIN, PARAMETER_MAX, probe_margin)
    sharpen_values = probe_values(PARAMETER_MIN, PARAMETER_MAX, probe_margin)
    denoised_cache: dict[float, np.ndarray] = {}
    variants: list[dict] = []
    crop_paths: list[str] = []

    for denoise in denoise_values:
        if denoise not in denoised_cache:
            denoised_cache[denoise] = build_denoised_base(image, denoise)
        denoised_base = denoised_cache[denoise]
        for sharpen in sharpen_values:
            rendered = render_processed_image(denoised_base, sharpen)
            destination = output_dir / f"denoise_{denoise:.1f}_sharpen_{sharpen:.1f}{source.suffix.lower()}"
            save_image_with_metadata(rendered, destination, metadata)
            variants.append(
                {
                    "output": str(destination),
                    "denoise": denoise,
                    "sharpen": sharpen,
                }
            )
            if test_crops:
                crop_dir = output_dir / "test"
                for crop in save_test_crops(
                    rendered,
                    crop_dir,
                    f"denoise_{denoise:.1f}_sharpen_{sharpen:.1f}",
                    source.suffix.lower(),
                    metadata,
                ):
                    crop_paths.append(str(crop))

    return {
        "mode": "test",
        "input": str(source),
        "output_dir": str(output_dir),
        "original": str(original_copy),
        "variants": variants,
        "test_crops": crop_paths,
    }
