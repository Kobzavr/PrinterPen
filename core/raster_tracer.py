"""
raster_tracer.py — High-fidelity vectorization and area infill for raster images.

Algorithms:
  1. Canny Edge Detection: Dual-threshold gradient detection (great for photos/sketches).
  2. Smooth Contour Trace: Adaptive/Otsu binarization with Chaikin spline subdivision
     (preserves natural curves, circles, and arcs without polygon faceting).
  3. Area Infill / Hatching: Geometric fill patterns strictly bounded inside solid dark
     regions (Linear Hatch, Cross-Hatch, Concentric Inset, Honeycomb, Triangles).
"""
from __future__ import annotations
from typing import List, Tuple, Optional
import os
import math
import tempfile
import subprocess
import shutil

import numpy as np
from PIL import Image

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

Polyline = List[Tuple[float, float]]


def chaikin_smooth(
    pts: List[Tuple[float, float]],
    iterations: int = 2,
    closed: bool = True,
    sharp_turn_threshold_deg: float = 50.0,
    max_cut_mm: float = 0.5,
) -> List[Tuple[float, float]]:
    """
    Subdivides polylines using corner-preserving Chaikin spline subdivision.
    - Preserves sharp acute corners and peaks without truncation or position drift.
    - Limits corner-cut distance on long straight edges (max_cut_mm) to maintain straightness.
    - Rounds out gentle pixel stair-steps on curves, circles, and arcs.
    """
    if iterations <= 0 or len(pts) < 3:
        return list(pts)

    curr = np.array(pts, dtype=np.float32)
    cos_threshold = math.cos(math.radians(sharp_turn_threshold_deg))

    for _ in range(iterations):
        n = len(curr)
        new_pts = []

        # Identify sharp corners where direction changes abruptly
        is_sharp = [False] * n
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                is_sharp[i] = True
                continue
            prev_pt = curr[(i - 1 + n) % n]
            pt = curr[i]
            next_pt = curr[(i + 1) % n]

            v_in = pt - prev_pt
            v_out = next_pt - pt
            len_in = math.hypot(v_in[0], v_in[1])
            len_out = math.hypot(v_out[0], v_out[1])

            if len_in > 1e-5 and len_out > 1e-5:
                cos_ang = (v_in[0] * v_out[0] + v_in[1] * v_out[1]) / (len_in * len_out)
                # Sharp turn (e.g. angle > 50 degrees)
                if cos_ang < cos_threshold:
                    is_sharp[i] = True

        limit = n if closed else n - 1
        for i in range(limit):
            p0 = curr[i]
            p1 = curr[(i + 1) % n]
            p0_sharp = is_sharp[i]
            p1_sharp = is_sharp[(i + 1) % n]

            edge_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            cut_ratio = 0.25
            if max_cut_mm > 0 and edge_len > 0:
                cut_ratio = min(0.25, max_cut_mm / edge_len)

            if p0_sharp:
                new_pts.append(p0)
            q = (1.0 - cut_ratio) * p0 + cut_ratio * p1
            r = cut_ratio * p0 + (1.0 - cut_ratio) * p1
            if not p0_sharp:
                new_pts.append(q)
            if not p1_sharp:
                new_pts.append(r)

        if not closed:
            new_pts.append(curr[-1])

        curr = np.array(new_pts, dtype=np.float32)

    return [(float(p[0]), float(p[1])) for p in curr]


def simplify_polyline_mm(
    pts: List[Tuple[float, float]],
    tolerance_mm: float = 0.035,
    min_dist_mm: float = 0.035,
    closed: bool = True,
) -> List[Tuple[float, float]]:
    """
    Simplifies polylines in millimeter space to eliminate micrometer jitter
    and reduce redundant points while preserving visual curvature and sharp corners.
    """
    if len(pts) < 3:
        return list(pts)

    # 1. Deduplicate points closer than min_dist_mm (e.g. 35 microns)
    cleaned = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) >= min_dist_mm:
            cleaned.append(p)

    if len(cleaned) < 3:
        return cleaned

    # 2. Douglas-Peucker simplification in mm coordinates
    if HAS_CV2 and tolerance_mm > 0:
        arr = np.array(cleaned, dtype=np.float32).reshape(-1, 1, 2)
        approx = cv2.approxPolyDP(arr, float(tolerance_mm), closed)
        res = [(float(p[0][0]), float(p[0][1])) for p in approx]
    else:
        res = cleaned

    if closed and len(res) >= 3:
        if math.hypot(res[0][0] - res[-1][0], res[0][1] - res[-1][1]) > 1e-4:
            res.append(res[0])

    return res


def load_image_as_gray(image_path: str) -> np.ndarray:
    """
    Loads image from disk converting to single-channel grayscale.
    Properly handles RGBA transparency by compositing transparent pixels onto pure white.
    """
    if not HAS_CV2:
        raise ImportError("opencv-python is not installed")

    raw = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    # Handle 4-channel RGBA / BGRA images (e.g. transparent PNGs)
    if len(raw.shape) == 3 and raw.shape[2] == 4:
        b, g, r, a = cv2.split(raw)
        alpha = a.astype(np.float32) / 255.0
        white = 255.0
        # Composite against white background so transparent regions become pure white
        b_comp = (b.astype(np.float32) * alpha + white * (1.0 - alpha)).astype(np.uint8)
        g_comp = (g.astype(np.float32) * alpha + white * (1.0 - alpha)).astype(np.uint8)
        r_comp = (r.astype(np.float32) * alpha + white * (1.0 - alpha)).astype(np.uint8)
        bgr = cv2.merge([b_comp, g_comp, r_comp])
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    elif len(raw.shape) == 3:
        return cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    else:
        return raw


# ── Method 1: Canny Edge Detection ────────────────────────────

def trace_raster_canny(
    image_path: str,
    threshold1: float = 50,
    threshold2: float = 150,
    blur_kernel: int = 3,
    target_width_mm: float = 100.0,
    min_contour_length: int = 5,
    epsilon_factor: float = 0.0012,
    smooth_level: int = 1,
) -> List[Polyline]:
    """Vectorizes image using OpenCV Canny edge detection with curvature preservation."""
    img = load_image_as_gray(image_path)
    h, w = img.shape
    scale_mm = target_width_mm / max(w, 1)

    if blur_kernel > 1:
        k = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
        blurred = cv2.GaussianBlur(img, (k, k), 0)
    else:
        blurred = img

    edges = cv2.Canny(blurred, int(threshold1), int(threshold2))

    # Clear 2-pixel border to eliminate artificial canvas frame edges
    edges[0:2, :] = 0
    edges[-2:, :] = 0
    edges[:, 0:2] = 0
    edges[:, -2:] = 0

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    polylines: List[Polyline] = []
    for contour in contours:
        if len(contour) < min_contour_length:
            continue

        # Fine polygon approximation to keep true curves
        arc_len = cv2.arcLength(contour, False)
        arc_len_mm = arc_len * scale_mm
        epsilon = epsilon_factor * arc_len
        approx = cv2.approxPolyDP(contour, epsilon, False)

        pts = [(float(p[0][0]) * scale_mm, float(p[0][1]) * scale_mm) for p in approx]

        eff_smooth = smooth_level
        if arc_len_mm < 3.0:
            eff_smooth = min(smooth_level, 1)

        if eff_smooth > 0 and len(pts) >= 4:
            pts = chaikin_smooth(pts, iterations=eff_smooth, closed=False)

        pts = simplify_polyline_mm(pts, tolerance_mm=0.035, min_dist_mm=0.035, closed=False)

        if len(pts) >= 2:
            polylines.append(pts)

    return polylines


# ── Method 2: Smooth Contour Trace ────────────────────────────

def trace_raster_contour_smooth(
    image_path: str,
    threshold: int = 128,
    auto_threshold: bool = True,
    invert: bool = False,
    blur_kernel: int = 3,
    target_width_mm: float = 100.0,
    min_contour_length: int = 5,
    smooth_level: int = 2,
) -> Tuple[List[Polyline], np.ndarray]:
    """
    Vectorizes image by binarizing into dark/light regions, followed by
    hierarchical contour extraction and Chaikin spline smoothing.
    Returns (polylines, binary_mask).
    """
    img = load_image_as_gray(image_path)
    h, w = img.shape
    scale_mm = target_width_mm / max(w, 1)

    if blur_kernel > 1:
        k = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
        blurred = cv2.GaussianBlur(img, (k, k), 0)
    else:
        blurred = img

    # Binarization: dark areas become 255 (active foreground for plotter)
    if auto_threshold:
        flag = (cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV) + cv2.THRESH_OTSU
        _, binary = cv2.threshold(blurred, 0, 255, flag)
    else:
        flag = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
        _, binary = cv2.threshold(blurred, int(threshold), 255, flag)

    # Clean single-pixel salt-and-pepper noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # Clear outer 2-pixel border to prevent artificial boundary frames
    binary[0:2, :] = 0
    binary[-2:, :] = 0
    binary[:, 0:2] = 0
    binary[:, -2:] = 0

    # Extract all external and internal contours
    contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)

    total_canvas_area = float(w * h)
    polylines: List[Polyline] = []
    for contour in contours:
        if len(contour) < min_contour_length:
            continue

        area = cv2.contourArea(contour)
        # Discard tiny speckles
        if area < 6:
            continue

        # Discard any outer boundary contour that encompasses almost the entire image
        if area >= (total_canvas_area * 0.98):
            continue

        # Fine approximation preserving curvature without stair-step bloating
        arc_len = cv2.arcLength(contour, True)
        arc_len_mm = arc_len * scale_mm
        epsilon = max(0.5, 0.0008 * arc_len)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        pts = [(float(p[0][0]) * scale_mm, float(p[0][1]) * scale_mm) for p in approx]

        eff_smooth = smooth_level
        if arc_len_mm < 3.0:
            eff_smooth = min(smooth_level, 1)

        if eff_smooth > 0 and len(pts) >= 4:
            pts = chaikin_smooth(pts, iterations=eff_smooth, closed=True)

        pts = simplify_polyline_mm(pts, tolerance_mm=0.035, min_dist_mm=0.035, closed=True)

        if len(pts) >= 3:
            if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
                pts.append(pts[0])  # Close loop
            polylines.append(pts)

    return polylines, binary


# ── Method 3: Centerline / Skeleton Trace ─────────────────────

def filter_polylines_by_length(
    polylines: List[Polyline],
    min_length_mm: float = 0.5,
) -> List[Polyline]:
    """Filters out micro-segments and tiny noise dots shorter than min_length_mm."""
    if min_length_mm <= 0:
        return polylines
    result: List[Polyline] = []
    for pl in polylines:
        if len(pl) < 2:
            continue
        total_len = sum(
            math.hypot(pl[i + 1][0] - pl[i][0], pl[i + 1][1] - pl[i][1])
            for i in range(len(pl) - 1)
        )
        if total_len >= min_length_mm:
            result.append(pl)
    return result


def zhang_suen_thinning(binary_mask: np.ndarray) -> np.ndarray:
    """
    Vectorized Zhang-Suen morphological thinning algorithm.
    Reduces binary foreground shapes to 1-pixel wide, 8-connected central medial axes (skeletons).
    """
    img = (binary_mask > 128).astype(np.uint8)
    prev = np.zeros_like(img)

    while True:
        # Step 1
        p2 = np.pad(img[:-1, :], ((1, 0), (0, 0)))
        p3 = np.pad(img[:-1, 1:], ((1, 0), (0, 1)))
        p4 = np.pad(img[:, 1:], ((0, 0), (0, 1)))
        p5 = np.pad(img[1:, 1:], ((0, 1), (0, 1)))
        p6 = np.pad(img[1:, :], ((0, 1), (0, 0)))
        p7 = np.pad(img[1:, :-1], ((0, 1), (1, 0)))
        p8 = np.pad(img[:, :-1], ((0, 0), (1, 0)))
        p9 = np.pad(img[:-1, :-1], ((1, 0), (1, 0)))

        neighbors = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
        transitions = (
            ((p2 == 0) & (p3 == 1)).astype(np.uint8) +
            ((p3 == 0) & (p4 == 1)).astype(np.uint8) +
            ((p4 == 0) & (p5 == 1)).astype(np.uint8) +
            ((p5 == 0) & (p6 == 1)).astype(np.uint8) +
            ((p6 == 0) & (p7 == 1)).astype(np.uint8) +
            ((p7 == 0) & (p8 == 1)).astype(np.uint8) +
            ((p8 == 0) & (p9 == 1)).astype(np.uint8) +
            ((p9 == 0) & (p2 == 1)).astype(np.uint8)
        )
        del_pts = (
            (img == 1)
            & (neighbors >= 2) & (neighbors <= 6)
            & (transitions == 1)
            & ((p2 * p4 * p6) == 0)
            & ((p4 * p6 * p8) == 0)
        )
        img[del_pts] = 0

        # Step 2
        p2 = np.pad(img[:-1, :], ((1, 0), (0, 0)))
        p3 = np.pad(img[:-1, 1:], ((1, 0), (0, 1)))
        p4 = np.pad(img[:, 1:], ((0, 0), (0, 1)))
        p5 = np.pad(img[1:, 1:], ((0, 1), (0, 1)))
        p6 = np.pad(img[1:, :], ((0, 1), (0, 0)))
        p7 = np.pad(img[1:, :-1], ((0, 1), (1, 0)))
        p8 = np.pad(img[:, :-1], ((0, 0), (1, 0)))
        p9 = np.pad(img[:-1, :-1], ((1, 0), (1, 0)))

        neighbors = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
        transitions = (
            ((p2 == 0) & (p3 == 1)).astype(np.uint8) +
            ((p3 == 0) & (p4 == 1)).astype(np.uint8) +
            ((p4 == 0) & (p5 == 1)).astype(np.uint8) +
            ((p5 == 0) & (p6 == 1)).astype(np.uint8) +
            ((p6 == 0) & (p7 == 1)).astype(np.uint8) +
            ((p7 == 0) & (p8 == 1)).astype(np.uint8) +
            ((p8 == 0) & (p9 == 1)).astype(np.uint8) +
            ((p9 == 0) & (p2 == 1)).astype(np.uint8)
        )
        del_pts = (
            (img == 1)
            & (neighbors >= 2) & (neighbors <= 6)
            & (transitions == 1)
            & ((p2 * p4 * p8) == 0)
            & ((p2 * p6 * p8) == 0)
        )
        img[del_pts] = 0

        if np.array_equal(img, prev):
            break
        prev = img.copy()

    return (img * 255).astype(np.uint8)


def skeleton_to_polylines(
    skel: np.ndarray,
    scale_mm: float = 1.0,
    min_length_mm: float = 0.5,
) -> List[Polyline]:
    """
    Extracts continuous polylines from a 1-pixel wide binary skeleton graph.
    Walks from leaf endpoints (deg 1) and branch junctions (deg >= 3), followed
    by closed cyclic loops (deg 2). Coordinates are converted to millimeters.
    """
    h, w = skel.shape
    skel_bool = skel > 0
    if not np.any(skel_bool):
        return []

    nbr_offsets = [
        (-1, -1), (-1, 0), (-1, 1),
        ( 0, -1),          ( 0, 1),
        ( 1, -1), ( 1, 0), ( 1, 1)
    ]
    padded = np.pad(skel_bool, 1, mode="constant", constant_values=False)
    deg = np.zeros_like(skel, dtype=np.uint8)
    for dy, dx in nbr_offsets:
        deg += padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    deg[~skel_bool] = 0

    visited_edges = set()
    polylines: List[Polyline] = []

    def get_nbrs(y: int, x: int):
        res = []
        for dy, dx in nbr_offsets:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and skel_bool[ny, nx]:
                res.append((ny, nx))
        return res

    ys, xs = np.where(skel_bool)
    nodes = []
    for y, x in zip(ys, xs):
        if deg[y, x] == 1 or deg[y, x] >= 3:
            nodes.append((int(y), int(x)))
    # Process leaf endpoints first so long strokes are continuous
    nodes.sort(key=lambda p: (deg[p[0], p[1]] != 1, p[0], p[1]))

    for sy, sx in nodes:
        for ny, nx in get_nbrs(sy, sx):
            edge_key = tuple(sorted([(sy, sx), (ny, nx)]))
            if edge_key in visited_edges:
                continue
            path = [(float(sx * scale_mm), float(sy * scale_mm)), (float(nx * scale_mm), float(ny * scale_mm))]
            visited_edges.add(edge_key)
            prev_y, prev_x = sy, sx
            curr_y, curr_x = ny, nx
            while deg[curr_y, curr_x] == 2:
                next_pt = None
                for n2y, n2x in get_nbrs(curr_y, curr_x):
                    if (n2y, n2x) != (prev_y, prev_x):
                        next_pt = (n2y, n2x)
                        break
                if next_pt is None:
                    break
                edge_key = tuple(sorted([(curr_y, curr_x), next_pt]))
                if edge_key in visited_edges:
                    break
                visited_edges.add(edge_key)
                prev_y, prev_x = curr_y, curr_x
                curr_y, curr_x = next_pt
                path.append((float(curr_x * scale_mm), float(curr_y * scale_mm)))

            len_mm = sum(
                math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
                for i in range(len(path) - 1)
            )
            if len_mm >= min_length_mm:
                polylines.append(path)

    # 2. Standalone cycles/loops (every pixel in cycle has deg == 2)
    for y, x in zip(ys, xs):
        y, x = int(y), int(x)
        if deg[y, x] == 2:
            for ny, nx in get_nbrs(y, x):
                edge_key = tuple(sorted([(y, x), (ny, nx)]))
                if edge_key not in visited_edges:
                    path = [(float(x * scale_mm), float(y * scale_mm)), (float(nx * scale_mm), float(ny * scale_mm))]
                    visited_edges.add(edge_key)
                    prev_y, prev_x = y, x
                    curr_y, curr_x = ny, nx
                    while True:
                        next_pt = None
                        for n2y, n2x in get_nbrs(curr_y, curr_x):
                            if (n2y, n2x) != (prev_y, prev_x):
                                next_pt = (n2y, n2x)
                                break
                        if next_pt is None:
                            break
                        edge_key = tuple(sorted([(curr_y, curr_x), next_pt]))
                        if edge_key in visited_edges:
                            break
                        visited_edges.add(edge_key)
                        prev_y, prev_x = curr_y, curr_x
                        curr_y, curr_x = next_pt
                        path.append((float(curr_x * scale_mm), float(curr_y * scale_mm)))
                    len_mm = sum(
                        math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
                        for i in range(len(path) - 1)
                    )
                    if len_mm >= min_length_mm:
                        polylines.append(path)

    return polylines


def trace_raster_centerline(
    image_path: str,
    threshold: int = 128,
    auto_threshold: bool = True,
    invert: bool = False,
    blur_kernel: int = 3,
    target_width_mm: float = 100.0,
    pen_width_mm: float = 0.5,
    min_path_len_mm: float = 0.5,
    smooth_level: int = 2,
    merge_close_lines: bool = True,
) -> Tuple[List[Polyline], np.ndarray]:
    """
    Vectorizes image using Centerline / Skeletonization (medial axis extraction).
    Instead of outlining both edges of a stroke (producing double lines),
    it traces a single continuous path down the center of each line.

    Also merges parallel strokes closer than pen width and eliminates speckles shorter
    than min_path_len_mm.
    """
    img = load_image_as_gray(image_path)
    h, w = img.shape
    scale_mm = target_width_mm / max(w, 1)
    px_per_mm = max(w, 1) / max(target_width_mm, 1.0)

    if blur_kernel > 1:
        k = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
        blurred = cv2.GaussianBlur(img, (k, k), 0)
    else:
        blurred = img

    # Binarization: dark strokes become 255
    if auto_threshold:
        flag = (cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV) + cv2.THRESH_OTSU
        _, binary = cv2.threshold(blurred, 0, 255, flag)
    else:
        flag = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
        _, binary = cv2.threshold(blurred, int(threshold), 255, flag)

    # Clear outer 2-pixel border
    binary[0:2, :] = 0
    binary[-2:, :] = 0
    binary[:, 0:2] = 0
    binary[:, -2:] = 0

    # Merge close parallel strokes / close narrow gaps with morphological closing
    if merge_close_lines and pen_width_mm > 0:
        close_px = max(2, int(round(pen_width_mm * px_per_mm * 0.75)))
        if close_px >= 2:
            k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_px, close_px))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k_close)

    # Pre-clean single-pixel salt-and-pepper noise
    kernel_clean = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_clean)

    # 1-pixel medial axis skeleton
    skel = zhang_suen_thinning(binary)

    # Extract polylines
    raw_polylines = skeleton_to_polylines(
        skel,
        scale_mm=scale_mm,
        min_length_mm=min_path_len_mm,
    )

    # Smooth and simplify
    polylines: List[Polyline] = []
    for pts in raw_polylines:
        if len(pts) < 2:
            continue
        arc_len_mm = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)
        )
        if arc_len_mm < min_path_len_mm:
            continue

        eff_smooth = smooth_level
        if arc_len_mm < 3.0:
            eff_smooth = min(smooth_level, 1)

        if eff_smooth > 0 and len(pts) >= 4:
            pts = chaikin_smooth(pts, iterations=eff_smooth, closed=False)

        pts = simplify_polyline_mm(pts, tolerance_mm=0.035, min_dist_mm=0.035, closed=False)
        if len(pts) >= 2:
            polylines.append(pts)

    return polylines, binary


# ── Area Infill / Hatching Engine ─────────────────────────────

def generate_infill(
    binary_mask: np.ndarray,
    target_width_mm: float,
    pattern: str = "linear",
    spacing_mm: float = 0.5,
    angle_deg: float = 45.0,
    min_area_mm2: float = 2.0,
    gray_img: Optional[np.ndarray] = None,
    invert: bool = False,
    infill_adaptive_range: int = 128,
) -> List[Polyline]:
    """
    Generates infill / hatching paths strictly bounded inside solid dark regions.
    Patterns:
      "linear"     — Parallel diagonal hatching with serpentine connections
      "crosshatch" — Double-pass grid at angle and angle + 90 deg
      "concentric" — Inset boundary shells following shape contours
      "honeycomb"  — Regular hexagonal mesh
      "triangles"  — Isometric triangular wireframe mesh
      "adaptive"   — Brightness-modulated density (dense shadows, sparse highlights)
    """
    if not HAS_CV2 or binary_mask is None or cv2.countNonZero(binary_mask) == 0:
        return []

    h, w = binary_mask.shape
    scale_mm = target_width_mm / max(w, 1)
    px_per_mm = max(w, 1) / max(target_width_mm, 1.0)
    spacing_px = max(2, int(round(spacing_mm * px_per_mm)))

    # Remove thin outline strokes using morphological open if min_area_mm2 >= 1.0.
    # For fine details or text (min_area_mm2 < 1.0), preserve the original strokes.
    if min_area_mm2 >= 1.0:
        min_thickness_px = max(3, int(round(spacing_px * 0.85)))
        if min_thickness_px % 2 == 0:
            min_thickness_px += 1
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (min_thickness_px, min_thickness_px))
        cleaned = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel_clean)
    else:
        cleaned = binary_mask

    # Filter connected regions below min_area_mm2
    min_area_px = min_area_mm2 * (px_per_mm ** 2)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    filtered_mask = np.zeros_like(cleaned)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area_px:
            filtered_mask[labels == i] = 255

    if cv2.countNonZero(filtered_mask) == 0:
        return []

    # Inward perimeter inset: erode the mask so infill lines NEVER bleed outside
    # or cross the smoothed perimeter contours.
    inset_ratio = 0.35 if min_area_mm2 >= 1.0 else 0.15
    inset_iter = max(1, int(round(spacing_px * inset_ratio)))
    kernel_inset = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    infill_mask = cv2.erode(filtered_mask, kernel_inset, iterations=inset_iter)

    if cv2.countNonZero(infill_mask) == 0:
        return []

    if pattern == "concentric":
        return _infill_concentric(infill_mask, spacing_px, scale_mm)
    elif pattern == "crosshatch":
        p1 = _infill_linear(infill_mask, angle_deg, spacing_px, scale_mm)
        p2 = _infill_linear(infill_mask, angle_deg + 90.0, spacing_px, scale_mm)
        return p1 + p2
    elif pattern == "honeycomb":
        return _infill_honeycomb(infill_mask, spacing_px, scale_mm)
    elif pattern == "triangles":
        return _infill_triangles(infill_mask, spacing_px, scale_mm)
    elif pattern == "adaptive" and gray_img is not None:
        return _infill_adaptive(
            gray_img=gray_img,
            target_width_mm=target_width_mm,
            base_spacing_mm=spacing_mm,
            angle_deg=angle_deg,
            min_area_mm2=min_area_mm2,
            binary_mask=infill_mask,
            invert=invert,
            adaptive_range=infill_adaptive_range,
        )
    else:  # default "linear"
        return _infill_linear(infill_mask, angle_deg, spacing_px, scale_mm)


def _infill_linear(
    mask: np.ndarray,
    angle_deg: float,
    spacing_px: int,
    scale_mm: float,
) -> List[Polyline]:
    """Generates continuous serpentine / zigzag linear hatching inside mask."""
    h, w = mask.shape
    center = (w / 2.0, h / 2.0)

    # Rotate mask so hatch lines run along horizontal image scanlines
    rot_mat = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
    cos = abs(rot_mat[0, 0])
    sin = abs(rot_mat[0, 1])
    nw = int(math.ceil((h * sin) + (w * cos)))
    nh = int(math.ceil((h * cos) + (w * sin)))
    rot_mat[0, 2] += (nw / 2) - center[0]
    rot_mat[1, 2] += (nh / 2) - center[1]

    rot_mask = cv2.warpAffine(mask, rot_mat, (nw, nh), flags=cv2.INTER_NEAREST)
    inv_rot_mat = cv2.invertAffineTransform(rot_mat)

    polylines: List[Polyline] = []
    current_poly: List[Tuple[float, float]] = []
    prev_rot_b: Optional[Tuple[float, float]] = None

    for y_idx, y in enumerate(range(spacing_px // 2, nh, spacing_px)):
        row = rot_mask[y, :]
        diff = np.diff(np.pad(row.astype(np.int16), (1, 1), 'constant'))
        starts = np.where(diff > 0)[0]
        ends = np.where(diff < 0)[0]

        segments = []
        for s, e in zip(starts, ends):
            if e - s >= 2:
                segments.append((float(s), float(e - 1)))

        if not segments:
            if current_poly:
                polylines.append(current_poly)
                current_poly = []
            prev_rot_b = None
            continue

        # Alternating direction for serpentine connection
        reverse = (y_idx % 2 == 1)

        if len(segments) == 1:
            x_a, x_b = segments[0]
            if reverse:
                x_a, x_b = x_b, x_a

            pt_a = inv_rot_mat @ np.array([x_a, float(y), 1.0])
            pt_b = inv_rot_mat @ np.array([x_b, float(y), 1.0])
            p_a = (float(pt_a[0]) * scale_mm, float(pt_a[1]) * scale_mm)
            p_b = (float(pt_b[0]) * scale_mm, float(pt_b[1]) * scale_mm)

            if current_poly and prev_rot_b is not None:
                last_pt = current_poly[-1]
                gap = math.hypot(p_a[0] - last_pt[0], p_a[1] - last_pt[1])

                # Verify connection path stays strictly inside rot_mask
                valid_connection = (gap <= spacing_px * scale_mm * 2.2)
                if valid_connection:
                    for t in (0.2, 0.4, 0.6, 0.8):
                        sx = int(round(prev_rot_b[0] * (1.0 - t) + x_a * t))
                        sy = int(round(prev_rot_b[1] * (1.0 - t) + float(y) * t))
                        if sx < 0 or sx >= nw or sy < 0 or sy >= nh or rot_mask[sy, sx] == 0:
                            valid_connection = False
                            break

                if valid_connection:
                    current_poly.append(p_a)
                    current_poly.append(p_b)
                else:
                    polylines.append(current_poly)
                    current_poly = [p_a, p_b]
            else:
                if current_poly:
                    polylines.append(current_poly)
                current_poly = [p_a, p_b]

            prev_rot_b = (x_b, float(y))
        else:
            prev_rot_b = None
            if current_poly:
                polylines.append(current_poly)
                current_poly = []
            for x_a, x_b in segments:
                pt_a = inv_rot_mat @ np.array([x_a, float(y), 1.0])
                pt_b = inv_rot_mat @ np.array([x_b, float(y), 1.0])
                polylines.append([
                    (float(pt_a[0]) * scale_mm, float(pt_a[1]) * scale_mm),
                    (float(pt_b[0]) * scale_mm, float(pt_b[1]) * scale_mm),
                ])

    if current_poly:
        polylines.append(current_poly)

    return polylines


def _infill_concentric(
    mask: np.ndarray,
    step_px: int,
    scale_mm: float,
) -> List[Polyline]:
    """Generates concentric offset shells eroding inward."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    curr_mask = mask.copy()
    polylines: List[Polyline] = []

    iterations_per_step = max(1, step_px)

    while cv2.countNonZero(curr_mask) >= 10:
        contours, _ = cv2.findContours(curr_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            if len(c) < 4 or cv2.contourArea(c) < 5:
                continue
            epsilon = max(0.4, 0.001 * cv2.arcLength(c, True))
            approx = cv2.approxPolyDP(c, epsilon, True)
            pts = [(float(p[0][0]) * scale_mm, float(p[0][1]) * scale_mm) for p in approx]
            if len(pts) >= 3:
                pts.append(pts[0])
                pts = chaikin_smooth(pts, iterations=1, closed=True)
                polylines.append(pts)
        curr_mask = cv2.erode(curr_mask, kernel, iterations=iterations_per_step)

    return polylines


def _infill_honeycomb(
    mask: np.ndarray,
    cell_size_px: int,
    scale_mm: float,
) -> List[Polyline]:
    """Generates regular hexagonal grid clipped inside the mask."""
    h, w = mask.shape
    r = max(4.0, cell_size_px / 2.0)
    dx = 1.5 * r
    dy = math.sqrt(3.0) * r

    cols = int(w / dx) + 2
    rows = int(h / dy) + 2

    edges = set()
    for col in range(-1, cols):
        for row in range(-1, rows):
            cx = col * dx
            cy = row * dy + (col % 2) * (dy / 2.0)
            pts = []
            for i in range(6):
                angle = math.pi / 3.0 * i
                px = round(cx + r * math.cos(angle), 1)
                py = round(cy + r * math.sin(angle), 1)
                pts.append((px, py))
            for i in range(6):
                p1, p2 = pts[i], pts[(i + 1) % 6]
                edges.add(tuple(sorted([p1, p2])))

    return _clip_edges_to_mask(edges, mask, scale_mm)


def _infill_triangles(
    mask: np.ndarray,
    cell_size_px: int,
    scale_mm: float,
) -> List[Polyline]:
    """Generates equilateral triangular wireframe mesh clipped inside the mask."""
    h, w = mask.shape
    side = max(4.0, float(cell_size_px))
    altitude = math.sqrt(3.0) / 2.0 * side

    cols = int(w / side) + 2
    rows = int(h / altitude) + 2

    edges = set()
    for row in range(-1, rows):
        y1 = row * altitude
        y2 = (row + 1) * altitude
        offset = (row % 2) * (side / 2.0)
        for col in range(-1, cols):
            x1 = col * side + offset
            x2 = x1 + side
            p_bl = (round(x1, 1), round(y1, 1))
            p_br = (round(x2, 1), round(y1, 1))
            p_top = (round(x1 + side / 2.0, 1), round(y2, 1))
            edges.add(tuple(sorted([p_bl, p_br])))
            edges.add(tuple(sorted([p_bl, p_top])))
            edges.add(tuple(sorted([p_br, p_top])))

    return _clip_edges_to_mask(edges, mask, scale_mm)


def _clip_edges_to_mask(
    edges: set,
    mask: np.ndarray,
    scale_mm: float,
) -> List[Polyline]:
    """Clips a set of 2D line segments strictly inside positive pixels of a mask."""
    h, w = mask.shape
    polylines: List[Polyline] = []

    for (p1, p2) in edges:
        x1, y1 = p1
        x2, y2 = p2
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(2, int(math.ceil(length)))
        xs = np.linspace(x1, x2, steps)
        ys = np.linspace(y1, y2, steps)

        valid = []
        for x, y in zip(xs, ys):
            ix, iy = int(round(x)), int(round(y))
            if 0 <= ix < w and 0 <= iy < h and mask[iy, ix] > 128:
                valid.append((x, y))
            else:
                if len(valid) >= 2:
                    polylines.append([
                        (valid[0][0] * scale_mm, valid[0][1] * scale_mm),
                        (valid[-1][0] * scale_mm, valid[-1][1] * scale_mm),
                    ])
                valid = []

        if len(valid) >= 2:
            polylines.append([
                (valid[0][0] * scale_mm, valid[0][1] * scale_mm),
                (valid[-1][0] * scale_mm, valid[-1][1] * scale_mm),
            ])

    return polylines


def _infill_adaptive(
    gray_img: np.ndarray,
    target_width_mm: float,
    base_spacing_mm: float,
    angle_deg: float,
    min_area_mm2: float,
    binary_mask: np.ndarray,
    invert: bool = False,
    adaptive_range: int = 128,
) -> List[Polyline]:
    """
    Generates brightness-modulated tonal infill / hatching paths.
    - Dark / shadow areas: dense parallel hatching (1x base spacing).
    - Mid-tones: medium parallel hatching (2x base spacing).
    - Light / gray areas: sparse hatching (4x base spacing).
    - Deep shadow regions (darkness >= 195): orthogonal cross-hatching at angle + 90°.
    - Pure white / highlight areas: left blank with zero lines.
    - adaptive_range: 20..240 (default 128). Sliding left (<128) makes drawing lighter.
    """
    if gray_img is None or binary_mask is None or cv2.countNonZero(binary_mask) == 0:
        return []

    h, w = binary_mask.shape[:2]
    if gray_img.shape[:2] != (h, w):
        gray_img = cv2.resize(gray_img, (w, h), interpolation=cv2.INTER_AREA)

    if len(gray_img.shape) == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)

    if invert:
        darkness = gray_img.astype(np.float32)
    else:
        darkness = 255.0 - gray_img.astype(np.float32)

    darkness = np.where(binary_mask > 0, darkness, 0)
    darkness = np.clip(darkness, 0, 255).astype(np.uint8)

    scale_mm = target_width_mm / max(w, 1)
    px_per_mm = max(w, 1) / max(target_width_mm, 1.0)
    base_spacing_px = max(2, int(round(base_spacing_mm * px_per_mm)))

    # Calculate tone thresholds based on user-adjustable adaptive_range (20..240, default 128)
    # Slide left (< 128) -> factor > 1.0 -> higher thresholds -> lighter drawing
    # Slide right (> 128) -> factor < 1.0 -> lower thresholds -> deeper/darker shading
    factor = (256.0 - float(np.clip(adaptive_range, 20, 240))) / 128.0
    thresh_light = int(np.clip(round(30 * factor), 5, 220))
    thresh_mid = int(np.clip(round(85 * factor), thresh_light + 8, 230))
    thresh_dense = int(np.clip(round(150 * factor), thresh_mid + 8, 245))
    thresh_shadow = int(np.clip(round(195 * factor), thresh_dense + 5, 254))

    pass1 = _trace_adaptive_pass(
        darkness=darkness,
        binary_mask=binary_mask,
        angle_deg=angle_deg,
        spacing_px=base_spacing_px,
        scale_mm=scale_mm,
        thresh_light=thresh_light,
        thresh_mid=thresh_mid,
        thresh_dense=thresh_dense,
    )

    pass2 = _trace_adaptive_shadow_pass(
        darkness=darkness,
        binary_mask=binary_mask,
        angle_deg=angle_deg + 90.0,
        spacing_px=base_spacing_px,
        scale_mm=scale_mm,
        shadow_thresh=thresh_shadow,
    )

    all_polylines = pass1 + pass2
    min_len = max(0.2, base_spacing_mm * 0.4)
    return filter_polylines_by_length(all_polylines, min_length_mm=min_len)


def _trace_adaptive_pass(
    darkness: np.ndarray,
    binary_mask: np.ndarray,
    angle_deg: float,
    spacing_px: int,
    scale_mm: float,
    thresh_light: int = 30,
    thresh_mid: int = 85,
    thresh_dense: int = 150,
) -> List[Polyline]:
    """
    Renders hatching lines at angle_deg where line density varies by tone:
      - Scanline k % 4 == 0: active if darkness >= thresh_light (light tones get 4x spacing)
      - Scanline k % 2 == 0: active if darkness >= thresh_mid   (mid tones get 2x spacing)
      - All scanlines:       active if darkness >= thresh_dense (dark tones get 1x spacing)
    """
    h, w = binary_mask.shape
    center = (w / 2.0, h / 2.0)

    rot_mat = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
    cos = abs(rot_mat[0, 0])
    sin = abs(rot_mat[0, 1])
    nw = int(math.ceil((h * sin) + (w * cos)))
    nh = int(math.ceil((h * cos) + (w * sin)))
    rot_mat[0, 2] += (nw / 2) - center[0]
    rot_mat[1, 2] += (nh / 2) - center[1]

    rot_mask = cv2.warpAffine(binary_mask, rot_mat, (nw, nh), flags=cv2.INTER_NEAREST)
    rot_dark = cv2.warpAffine(darkness, rot_mat, (nw, nh), flags=cv2.INTER_LINEAR)
    inv_rot_mat = cv2.invertAffineTransform(rot_mat)

    polylines: List[Polyline] = []
    current_poly: List[Tuple[float, float]] = []
    prev_rot_b: Optional[Tuple[float, float]] = None
    prev_y: Optional[int] = None

    min_seg_len_px = max(2, int(round(spacing_px * 0.4)))
    y_indices = list(range(spacing_px // 2, nh, spacing_px))

    for k, y in enumerate(y_indices):
        if k % 4 == 0:
            thresh = thresh_light
        elif k % 2 == 0:
            thresh = thresh_mid
        else:
            thresh = thresh_dense

        row_mask = rot_mask[y, :]
        row_dark = rot_dark[y, :]

        active = (row_mask > 128) & (row_dark >= thresh)
        if not np.any(active):
            if current_poly:
                polylines.append(current_poly)
                current_poly = []
            prev_rot_b = None
            prev_y = None
            continue

        # CRITICAL: Convert uint8 to int16 before np.diff to avoid unsigned subtraction underflow
        diff = np.diff(np.pad(active.astype(np.int16), (1, 1), 'constant'))
        starts = np.where(diff > 0)[0]
        ends = np.where(diff < 0)[0]

        segments = []
        for s, e in zip(starts, ends):
            if e - s >= min_seg_len_px:
                segments.append((float(s), float(e - 1)))

        if not segments:
            if current_poly:
                polylines.append(current_poly)
                current_poly = []
            prev_rot_b = None
            prev_y = None
            continue

        reverse = (k % 2 == 1)

        if len(segments) == 1 and prev_y is not None and (y - prev_y == spacing_px):
            x_a, x_b = segments[0]
            if reverse:
                x_a, x_b = x_b, x_a

            pt_a = inv_rot_mat @ np.array([x_a, float(y), 1.0])
            pt_b = inv_rot_mat @ np.array([x_b, float(y), 1.0])
            p_a = (float(pt_a[0]) * scale_mm, float(pt_a[1]) * scale_mm)
            p_b = (float(pt_b[0]) * scale_mm, float(pt_b[1]) * scale_mm)

            if current_poly and prev_rot_b is not None:
                last_pt = current_poly[-1]
                gap = math.hypot(p_a[0] - last_pt[0], p_a[1] - last_pt[1])
                valid_connection = (gap <= spacing_px * scale_mm * 2.2)
                if valid_connection:
                    mid_y = int(round((prev_rot_b[1] + y) / 2.0))
                    mid_x = int(round(prev_rot_b[0]))
                    if 0 <= mid_y < nh and 0 <= mid_x < nw:
                        if rot_mask[mid_y, mid_x] == 0:
                            valid_connection = False

                if valid_connection:
                    current_poly.append(p_a)
                    current_poly.append(p_b)
                else:
                    polylines.append(current_poly)
                    current_poly = [p_a, p_b]
            else:
                current_poly = [p_a, p_b]

            prev_rot_b = (x_b, float(y))
            prev_y = y
        else:
            if current_poly:
                polylines.append(current_poly)
                current_poly = []
            prev_rot_b = None
            prev_y = None

            for x_a, x_b in segments:
                pt_a = inv_rot_mat @ np.array([x_a, float(y), 1.0])
                pt_b = inv_rot_mat @ np.array([x_b, float(y), 1.0])
                p_a = (float(pt_a[0]) * scale_mm, float(pt_a[1]) * scale_mm)
                p_b = (float(pt_b[0]) * scale_mm, float(pt_b[1]) * scale_mm)
                polylines.append([p_a, p_b])

    if current_poly:
        polylines.append(current_poly)

    return polylines


def _trace_adaptive_shadow_pass(
    darkness: np.ndarray,
    binary_mask: np.ndarray,
    angle_deg: float,
    spacing_px: int,
    scale_mm: float,
    shadow_thresh: int = 195,
) -> List[Polyline]:
    """
    Renders orthogonal cross-hatching strictly in the deepest shadow areas (darkness >= shadow_thresh).
    """
    h, w = binary_mask.shape
    center = (w / 2.0, h / 2.0)

    rot_mat = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
    cos = abs(rot_mat[0, 0])
    sin = abs(rot_mat[0, 1])
    nw = int(math.ceil((h * sin) + (w * cos)))
    nh = int(math.ceil((h * cos) + (w * sin)))
    rot_mat[0, 2] += (nw / 2) - center[0]
    rot_mat[1, 2] += (nh / 2) - center[1]

    rot_mask = cv2.warpAffine(binary_mask, rot_mat, (nw, nh), flags=cv2.INTER_NEAREST)
    rot_dark = cv2.warpAffine(darkness, rot_mat, (nw, nh), flags=cv2.INTER_LINEAR)
    inv_rot_mat = cv2.invertAffineTransform(rot_mat)

    polylines: List[Polyline] = []
    min_seg_len_px = max(2, int(round(spacing_px * 0.4)))

    for y in range(spacing_px // 2, nh, spacing_px):
        row_mask = rot_mask[y, :]
        row_dark = rot_dark[y, :]

        active = (row_mask > 128) & (row_dark >= shadow_thresh)
        if not np.any(active):
            continue

        diff = np.diff(np.pad(active.astype(np.int16), (1, 1), 'constant'))
        starts = np.where(diff > 0)[0]
        ends = np.where(diff < 0)[0]

        for s, e in zip(starts, ends):
            if e - s >= min_seg_len_px:
                pt_a = inv_rot_mat @ np.array([float(s), float(y), 1.0])
                pt_b = inv_rot_mat @ np.array([float(e - 1), float(y), 1.0])
                polylines.append([
                    (float(pt_a[0]) * scale_mm, float(pt_a[1]) * scale_mm),
                    (float(pt_b[0]) * scale_mm, float(pt_b[1]) * scale_mm),
                ])

    return polylines


# ── Unified Tracing Function ──────────────────────────────────

def trace_raster_full(
    image_path: str,
    target_width_mm: float = 100.0,
    method: str = "contour",
    threshold1: float = 50,
    threshold2: float = 150,
    contour_thresh: int = 128,
    auto_thresh: bool = True,
    invert: bool = False,
    smooth_level: int = 2,
    enable_infill: bool = False,
    infill_pattern: str = "linear",
    infill_spacing_mm: float = 0.5,
    infill_angle: float = 45.0,
    infill_min_area_mm2: float = 2.0,
    pen_width_mm: float = 0.5,
    min_path_len_mm: float = 0.5,
    merge_close_lines: bool = True,
    infill_adaptive_range: int = 128,
) -> Tuple[List[Polyline], List[Polyline]]:
    """
    Unified entry point vectorizing a raster image into:
      (contour_polylines, infill_polylines)
    """
    if method == "canny":
        contours = trace_raster_canny(
            image_path=image_path,
            threshold1=threshold1,
            threshold2=threshold2,
            target_width_mm=target_width_mm,
            smooth_level=smooth_level,
        )
        if min_path_len_mm > 0:
            contours = filter_polylines_by_length(contours, min_path_len_mm)
        binary_mask = None
        if enable_infill and HAS_CV2:
            img = load_image_as_gray(image_path)
            if img is not None:
                _, binary_mask = cv2.threshold(
                    img, 0 if auto_thresh else contour_thresh, 255,
                    (cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV) +
                    (cv2.THRESH_OTSU if auto_thresh else 0)
                )
                binary_mask[0:2, :] = 0
                binary_mask[-2:, :] = 0
                binary_mask[:, 0:2] = 0
                binary_mask[:, -2:] = 0
    elif method == "centerline":
        contours, binary_mask = trace_raster_centerline(
            image_path=image_path,
            threshold=contour_thresh,
            auto_threshold=auto_thresh,
            invert=invert,
            target_width_mm=target_width_mm,
            pen_width_mm=pen_width_mm,
            min_path_len_mm=min_path_len_mm,
            smooth_level=smooth_level,
            merge_close_lines=merge_close_lines,
        )
    else:  # "contour"
        contours, binary_mask = trace_raster_contour_smooth(
            image_path=image_path,
            threshold=contour_thresh,
            auto_threshold=auto_thresh,
            invert=invert,
            target_width_mm=target_width_mm,
            smooth_level=smooth_level,
        )
        if min_path_len_mm > 0:
            contours = filter_polylines_by_length(contours, min_path_len_mm)

    infill: List[Polyline] = []
    if enable_infill and binary_mask is not None:
        gray_source = None
        if infill_pattern == "adaptive":
            try:
                gray_source = load_image_as_gray(image_path)
            except Exception as e:
                print(f"Could not load grayscale image for adaptive infill: {e}")
        infill = generate_infill(
            binary_mask=binary_mask,
            target_width_mm=target_width_mm,
            pattern=infill_pattern,
            spacing_mm=infill_spacing_mm,
            angle_deg=infill_angle,
            min_area_mm2=infill_min_area_mm2,
            gray_img=gray_source,
            invert=invert,
            infill_adaptive_range=infill_adaptive_range,
        )

    return contours, infill


# ── Color Palette Infill Engine ───────────────────────────────

def extract_color_palette(
    rgba_img: np.ndarray,
    max_colors: int = 8,
    min_pct: float = 1.0,
) -> List[dict]:
    """
    Analyzes an RGBA or RGB image array and extracts dominant color clusters.
    Filters out transparent and pure/near-white background pixels.
    """
    if rgba_img is None or rgba_img.size == 0:
        return []

    h, w = rgba_img.shape[:2]
    if len(rgba_img.shape) == 2:
        rgb = np.stack([rgba_img, rgba_img, rgba_img], axis=-1)
        a = np.ones((h, w), dtype=np.uint8) * 255
    elif rgba_img.shape[2] == 4:
        r = rgba_img[:, :, 0]
        g = rgba_img[:, :, 1]
        b = rgba_img[:, :, 2]
        a = rgba_img[:, :, 3]
        rgb = np.stack([r, g, b], axis=-1)
    else:
        rgb = rgba_img[:, :, :3]
        a = np.ones((h, w), dtype=np.uint8) * 255

    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]

    valid = (a > 50) & ~((r > 245) & (g > 245) & (b > 245))
    colored_pixels = rgb[valid]
    total_colored = len(colored_pixels)
    if total_colored == 0:
        return []

    quant = (colored_pixels.astype(np.int32) // 32) * 32 + 16
    quant = np.clip(quant, 0, 255)

    from collections import Counter
    color_keys = [f"#{p[0]:02x}{p[1]:02x}{p[2]:02x}" for p in quant]
    counts = Counter(color_keys)

    palette = []
    default_patterns = ["linear", "crosshatch", "concentric", "honeycomb", "triangles", "linear"]
    default_angles = [45.0, 135.0, 0.0, 45.0, 60.0, 90.0]

    idx = 0
    for hex_code, count in counts.most_common(max_colors):
        pct = (count / total_colored) * 100.0
        if pct < min_pct and len(palette) >= 2:
            continue
        cr = int(hex_code[1:3], 16)
        cg = int(hex_code[3:5], 16)
        cb = int(hex_code[5:7], 16)
        pat = default_patterns[idx % len(default_patterns)]
        ang = default_angles[idx % len(default_angles)]
        palette.append({
            "hex": hex_code,
            "rgb": (cr, cg, cb),
            "pct": round(pct, 1),
            "enabled": True,
            "pattern": pat,
            "angle_deg": ang,
            "spacing_mm": 0.5,
        })
        idx += 1

    return palette


def generate_palette_infill(
    rgba_img: np.ndarray,
    target_width_mm: float,
    color_configs: List[dict],
    color_tolerance: float = 48.0,
) -> List[Tuple[str, List[Polyline]]]:
    """
    Generates infill polylines for each enabled color cluster.
    Returns: List of (hex_color, polylines) pairs.
    """
    if rgba_img is None or rgba_img.size == 0 or not color_configs:
        return []

    h, w = rgba_img.shape[:2]
    if len(rgba_img.shape) == 2:
        rgb = np.stack([rgba_img, rgba_img, rgba_img], axis=-1)
        a = np.ones((h, w), dtype=np.uint8) * 255
    elif rgba_img.shape[2] == 4:
        rgb = rgba_img[:, :, :3]
        a = rgba_img[:, :, 3]
    else:
        rgb = rgba_img[:, :, :3]
        a = np.ones((h, w), dtype=np.uint8) * 255

    results: List[Tuple[str, List[Polyline]]] = []

    for cfg in color_configs:
        if not cfg.get("enabled", True):
            continue

        cr, cg, cb = cfg["rgb"]
        target = np.array([cr, cg, cb], dtype=np.float32)
        dist = np.linalg.norm(rgb.astype(np.float32) - target, axis=-1)

        mask = ((dist <= color_tolerance) & (a > 50)).astype(np.uint8) * 255
        mask[0:2, :] = 0
        mask[-2:, :] = 0
        mask[:, 0:2] = 0
        mask[:, -2:] = 0

        if cv2.countNonZero(mask) == 0:
            continue

        strokes = generate_infill(
            binary_mask=mask,
            target_width_mm=target_width_mm,
            pattern=cfg.get("pattern", "linear"),
            spacing_mm=cfg.get("spacing_mm", 0.5),
            angle_deg=cfg.get("angle_deg", 45.0),
            min_area_mm2=cfg.get("min_area_mm2", 1.0),
        )
        if strokes:
            results.append((cfg["hex"], strokes))

    return results
