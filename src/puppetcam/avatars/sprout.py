"""Sprout: the default avatar. A round character, styled by a theme.

Drawn entirely with OpenCV polygon fills (anti-aliased, sub-pixel), so it
costs a couple of milliseconds per frame on one CPU core. The "3D" is faked
with parallax: when the head turns, facial features slide and the far-side
eye narrows, ears move the opposite way, and a shadow crescent appears.
The leaf has a damped spring, so it lags and bounces when you move.

Colors, proportions and accessories come from ``self.theme`` (see themes.py).
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from ..params import AvatarParams
from ..themes import Theme
from .base import Avatar

SHIFT = 4  # sub-pixel bits for cv2 drawing
ONE = 1 << SHIFT


def _circle(n: int) -> np.ndarray:
    a = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    return np.stack([np.cos(a), np.sin(a)], axis=1)


def _superellipse(n: int, p: float) -> np.ndarray:
    c = _circle(n)
    return np.sign(c) * np.abs(c) ** (2.0 / p)


class SproutAvatar(Avatar):
    name = "sprout"

    def __init__(self, width: int, height: int, badge: bool = True, theme: Theme | None = None) -> None:
        super().__init__(width, height, badge, theme)
        self.c = self.theme.colors
        self.s = self.theme.shape
        self.acc = set(self.theme.accessories)
        self.R = 0.27 * height  # head radius in pixels: everything scales from it
        self.cx = width / 2.0
        self.cy = 0.50 * height
        self._circle = _circle(40)
        self.top = -self.s["head_aspect"]  # y of the top of the head, local units
        self._head = _superellipse(72, self.s["head_roundness"]) * np.array([1.0, self.s["head_aspect"]])
        self._hat, self._band = self._make_hat()
        self._bg = self._make_background()
        self._out = np.empty_like(self._bg)
        self._leaf_world = 0.0  # spring state, radians
        self._leaf_vel = 0.0

    # ---------------------------------------------------------------- setup
    def _make_background(self) -> np.ndarray:
        h, w = self.height, self.width
        image_path = self.theme.background_image
        if image_path is not None:
            img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"Cannot read background image: {image_path}")
            scale = max(w / img.shape[1], h / img.shape[0])  # cover, then center-crop
            img = cv2.resize(img, (math.ceil(img.shape[1] * scale), math.ceil(img.shape[0] * scale)),
                             interpolation=cv2.INTER_AREA)
            y0, x0 = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
            return np.ascontiguousarray(img[y0 : y0 + h, x0 : x0 + w])
        top = np.array(self.c["background_top"], np.float32)
        bottom = np.array(self.c["background_bottom"], np.float32)
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        bg = np.broadcast_to(top * (1.0 - y) + bottom * y, (h, w, 3)).copy()
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d2 = ((xx - self.cx) ** 2 + (yy - self.cy) ** 2) / (1.7 * self.R) ** 2
        halo = np.exp(-d2)[..., None] * 0.55
        bg = bg * (1.0 - halo) + np.array(self.c["halo"], np.float32) * halo
        return np.clip(bg, 0, 255).astype(np.uint8)

    def _make_hat(self) -> tuple[np.ndarray, np.ndarray]:
        """Beanie = the top of the head outline, a bit larger, cut at the forehead."""
        cut = self.top * 0.5
        self._hat_cut = cut
        outline = self._head * 1.06
        crown = outline[outline[:, 1] < cut]
        u = np.linspace(1.0, -1.0, 15)
        x_edge = np.abs(crown[:, 0]).max()
        rim = np.stack([u * x_edge, cut + 0.03 * (1 - u**2)], axis=1)
        band = np.stack([u[::-1] * x_edge * 0.99, cut - 0.02 + 0.03 * (1 - u**2)], axis=1)
        return np.concatenate([crown, rim]), band

    # -------------------------------------------------------------- helpers
    def _to_px(self, pts: np.ndarray, origin: tuple[float, float], roll: float,
               pivot: tuple[float, float] = (0.0, 0.95)) -> np.ndarray:
        """Local head units -> fixed-point pixels, rotated by roll around pivot."""
        p = (pts - pivot) * self.R
        c, s = math.cos(roll), math.sin(roll)
        x = c * p[:, 0] - s * p[:, 1] + pivot[0] * self.R + origin[0]
        y = s * p[:, 0] + c * p[:, 1] + pivot[1] * self.R + origin[1]
        return np.round(np.stack([x, y], axis=1) * ONE).astype(np.int32)

    def _ellipse(self, cx: float, cy: float, ax: float, ay: float, angle: float = 0.0) -> np.ndarray:
        c, s = math.cos(angle), math.sin(angle)
        e = self._circle * (ax, ay)
        return np.stack([c * e[:, 0] - s * e[:, 1] + cx, s * e[:, 0] + c * e[:, 1] + cy], axis=1)

    def _fill(self, pts: np.ndarray, color) -> None:
        cv2.fillPoly(self._out, [pts], color, cv2.LINE_AA, SHIFT)

    def _stroke(self, pts: np.ndarray, color, width: float, closed: bool = False) -> None:
        t = max(1, round(width * self.R))
        cv2.polylines(self._out, [pts], closed, color, t, cv2.LINE_AA, SHIFT)

    def _update_leaf(self, head_angle: float, dt: float) -> float:
        dt = min(max(dt, 0.0), 0.05)
        k, c = 90.0, 9.0  # stiffness, damping (slightly bouncy)
        for _ in range(2):
            h = dt / 2.0
            acc = k * (head_angle - self._leaf_world) - c * self._leaf_vel
            self._leaf_vel += acc * h
            self._leaf_world += self._leaf_vel * h
        return float(np.clip(self._leaf_world - head_angle, -0.9, 0.9))

    # --------------------------------------------------------------- render
    def render(self, p: AvatarParams, dt: float) -> np.ndarray:
        np.copyto(self._out, self._bg)
        c, s, R = self.c, self.s, self.R
        yaw, pitch, roll = p.yaw, p.pitch, p.roll
        breath = p.breath

        # Body: barely rolls, rises with breath.
        body_origin = (self.cx + yaw * 0.04 * R, self.cy - breath * 0.025 * R)
        body_roll = roll * 0.25
        bw = s["body_width"]

        def body(pts: np.ndarray) -> np.ndarray:
            return self._to_px(pts, body_origin, body_roll)

        self._fill(body(self._ellipse(0, 1.78, 1.38 * bw, 0.86)), c["sweater_shade"])
        self._fill(body(self._ellipse(0.05 * yaw, 1.80, 1.30 * bw, 0.80)), c["sweater"])
        self._fill(body(self._ellipse(0.04 * yaw, 0.98, 0.30, 0.26)), c["neck"])

        head_origin = (self.cx + yaw * 0.05 * R, self.cy - pitch * 0.03 * R - breath * 0.012 * R)

        def head(pts: np.ndarray) -> np.ndarray:
            return self._to_px(pts, head_origin, roll)

        # Leaf: rotates around its base on top of the head, with spring lag.
        lag = self._update_leaf(roll + yaw * 0.5, dt)
        if "sprout" in self.acc:
            base = np.array([0.0, self.top + 0.07])
            tip_angle = lag * 0.9
            k = np.linspace(0.0, 1.0, 8)
            bend = tip_angle * k  # the stem curves more toward the tip
            stem = base + 0.38 * k[:, None] * np.stack([np.sin(bend), -np.cos(bend)], axis=1)
            tip = stem[-1]
            self._stroke(head(stem), c["stem"], 0.05)
            self._fill(head(self._ellipse(tip[0] - 0.13, tip[1] - 0.02, 0.15, 0.065, -0.5 + tip_angle)),
                       c["leaf_dark"])
            self._fill(head(self._ellipse(tip[0] + 0.14, tip[1] - 0.06, 0.17, 0.07, 0.45 + tip_angle)),
                       c["leaf_light"])

        # Ears (and headphone cups): parallax opposite to the turn.
        ear_x = {side: side * 0.97 - yaw * 0.10 for side in (-1.0, 1.0)}
        for side in (-1.0, 1.0):
            self._fill(head(self._ellipse(ear_x[side], 0.02, 0.17, 0.22)), c["skin_shade"])
            self._fill(head(self._ellipse(ear_x[side] + side * 0.02, 0.02, 0.09, 0.13)), c["ear_inner"])
        phones = "headphones" in self.acc
        far_side = 1.0 if yaw > 0 else -1.0
        if phones and abs(yaw) > 0.15:  # the far cup goes behind the head
            self._cup(head, ear_x[far_side], far_side)

        # Head with a shadow crescent on the side that turns away.
        self._fill(head(self._head), c["skin_shade"])
        lit = self._head * 0.965 + (yaw * 0.07, -0.015 - pitch * 0.02)
        self._fill(head(lit), c["skin"])

        # Facial features slide with the turn and compress toward the edges.
        fx, fy = yaw * 0.30, -pitch * 0.22
        squash = 1.0 - 0.18 * abs(yaw)

        def fpos(x: float, y: float, depth: float = 1.0) -> tuple[float, float]:
            return x * squash + fx * depth, y + fy * depth

        # Cheeks: blush deepens with a smile.
        warmth = 0.35 + 0.5 * max(p.smile, 0.0)
        skin, blush_c = np.array(c["skin"], np.float32), np.array(c["blush"], np.float32)
        blush = tuple(int(v) for v in skin * (1 - warmth) + blush_c * warmth)
        for side in (-1.0, 1.0):
            sx = 1.0 - 0.45 * max(0.0, side * yaw)
            bx, by = fpos(side * 0.60, 0.25, 0.9)
            self._fill(head(self._ellipse(bx, by, 0.13 * sx, 0.075)), blush)

        # Eyes and brows.
        es, spacing = s["eye_size"], 0.38 * s["eye_spacing"]
        lens_centers = []
        for side, open_ in ((-1.0, p.eye_open_l), (1.0, p.eye_open_r)):
            sx = 1.0 - 0.40 * max(0.0, side * yaw)  # far-side eye narrows
            ex0, ey0 = fpos(side * spacing, -0.02)
            lens_centers.append((ex0, ey0, sx))
            ex, ey = ex0 + p.gaze_x * 0.05, ey0 - p.gaze_y * 0.04
            if open_ < 0.15:
                half = 0.10 * sx * es
                xs = np.linspace(-half, half, 9)
                arc = np.stack([ex + xs, ey + 1.6 * (half**2 - xs**2)], axis=1)  # lid line ‿
                self._stroke(head(arc), c["eye"], 0.045)
            else:
                self._fill(head(self._ellipse(ex, ey, 0.11 * sx * es, 0.165 * open_ * es)), c["eye"])
                if open_ > 0.45:
                    shine = self._ellipse(ex - 0.035 * sx * es, ey - 0.06 * open_ * es,
                                          0.035 * sx * es, 0.04 * es)
                    self._fill(head(shine), c["eye_shine"])
            # Brow: raised = up and a bit worried, frown = inner end down.
            by = ey - 0.29 * (0.6 + 0.4 * es) - p.brow * 0.07
            if "beanie" in self.acc:  # keep brows visible under the hat band
                by = max(by, self._hat_cut + 0.10)
            inner_dy = -min(p.brow, 0.0) * 0.07 - max(p.brow, 0.0) * 0.03
            x_in, x_out = ex - side * 0.09 * sx, ex + side * 0.10 * sx
            brow = np.array([[x_in, by + inner_dy - 0.01], [x_out, by + 0.01]])  # friendly at rest
            self._stroke(head(brow), c["brow"], 0.055)

        # Mouth: a curve when closed, a filled shape with a tongue when open.
        mx, my = fpos(0.0, 0.40, 1.1)
        hw = 0.17 * s["mouth_width"] * (1.0 + 0.25 * p.smile) * (1.0 - 0.3 * abs(yaw))
        u = np.linspace(-1.0, 1.0, 17)
        top_y = my - p.smile * 0.07 * u**2
        top = np.stack([mx + u * hw, top_y], axis=1)
        if p.mouth_open < 0.06:
            self._stroke(head(top), c["mouth"], 0.04)
        else:
            h = 0.30 * p.mouth_open
            bottom = np.stack([mx + u * hw, top_y + h * (1.0 - u**2) ** 0.6], axis=1)[::-1]
            self._fill(head(np.concatenate([top, bottom])), c["mouth"])
            if p.mouth_open > 0.25:
                self._fill(head(self._ellipse(mx, my + h * 0.70, hw * 0.45, h * 0.26)), c["tongue"])

        # Accessories that sit on top of the face.
        if "beanie" in self.acc:
            self._fill(head(self._hat), c["hat"])
            self._stroke(head(self._band), c["hat_band"], 0.11)
            if "sprout" not in self.acc:
                self._fill(head(self._ellipse(0.0, self.top * 1.08 - 0.06, 0.13, 0.12)), c["hat_band"])
        if "glasses" in self.acc:
            for ex0, ey0, sx in lens_centers:
                ring = self._ellipse(ex0, ey0 + 0.01, 0.19 * sx * es, 0.17 * es)
                self._stroke(head(ring), c["glasses"], 0.035, closed=True)
            (lx, ly, lsx), (rx, ry, rsx) = lens_centers
            bridge = np.array([[lx + 0.19 * lsx * es, ly - 0.01], [rx - 0.19 * rsx * es, ry - 0.01]])
            self._stroke(head(bridge), c["glasses"], 0.035)
        if phones:
            arc = self._head * np.array([1.12, 1.16])  # a gap above the head: reads as a band, not hair
            band = arc[arc[:, 1] < self.top * 0.25]
            band = band[np.argsort(band[:, 0])]
            self._stroke(head(band), c["headphones"], 0.07)
            for side in (-1.0, 1.0):
                if abs(yaw) > 0.15 and side == far_side:
                    continue  # already drawn behind the head
                self._cup(head, ear_x[side], side)

        if self.badge:
            self._draw_badge()
        return self._out

    def _cup(self, head, x: float, side: float) -> None:
        self._fill(head(self._ellipse(x, 0.03, 0.17, 0.26)), self.c["headphones"])
        self._fill(head(self._ellipse(x - side * 0.04, 0.03, 0.09, 0.18)), self.c["headphones_pad"])

    def _draw_badge(self) -> None:
        scale = self.height / 720.0
        text = "AVATAR"
        font = cv2.FONT_HERSHEY_SIMPLEX
        fs, th = 0.6 * scale * 1.4, max(1, round(2 * scale))
        (tw, tht), _ = cv2.getTextSize(text, font, fs, th)
        pad = round(10 * scale)
        x0, y1 = round(18 * scale), self.height - round(18 * scale)
        x1, y0 = x0 + tw + 2 * pad, y1 - tht - 2 * pad
        cv2.rectangle(self._out, (x0, y0), (x1, y1), (40, 30, 25), -1, cv2.LINE_AA)
        cv2.putText(self._out, text, (x0 + pad, y1 - pad), font, fs, (235, 235, 235), th, cv2.LINE_AA)
