import warnings
import math

from itertools import cycle

try:
    from itertools import izip
except ImportError:
    izip = zip

from PyQt5.QtGui import QPainter
from PyQt5.QtGui import QPaintDevice
from PyQt5.QtGui import QPaintEngine

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QLineF

from PyQt5.QtGui import QPen
from PyQt5.QtGui import QTransform


def split_line(line, offset):
    if offset <= 0:
        return [], line

    for i, ((x1, y1), (x2, y2)) in enumerate(zip(line, line[1:])):
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt((dx * dx) + (dy * dy))

        if length < offset:
            offset -= length
        elif length == offset:
            before = line[: i + 2]
            after = line[i + 1 :]

            if len(after) == 1:
                after = []

            return before, after
        else:
            xm = x1 + (dx * (offset / length))
            ym = y1 + (dy * (offset / length))
            before = line[: i + 1] + [(xm, ym)]
            after = [(xm, ym)] + line[i + 1 :]
            return before, after

    return line, []


def dash_line(line, dash_pattern, dash_offset=0):
    if len(dash_pattern) % 2 != 0:
        warnings.warn(
            "Dash pattern with non-even number of lengths; ignoring final length."
        )
        dash_pattern = dash_pattern[:-1]

    if not dash_pattern or len(line) <= 1:
        return [line]

    pattern_length = sum(dash_pattern)
    dash_offset %= pattern_length

    dash_iter = iter(izip(cycle(dash_pattern), cycle([True, False])))
    for dash_length, dash_on in dash_iter:
        if dash_length <= dash_offset:
            dash_offset -= dash_length
        else:
            dash_length -= dash_offset
            break

    out = []
    while line:
        before, line = split_line(line, dash_length)
        if dash_on:
            out.append(before)
        dash_length, dash_on = next(dash_iter)

    return out


class OutlinePaintEngine(QPaintEngine):
    def __init__(self, paint_device):
        super().__init__(QPaintEngine.AllFeatures)

        self._transform = QTransform()
        self._pen = QPen()
        self._opacity = 1.0

        self._outlines = []

    def getOutlines(self):
        return self._outlines

    def begin(self, paint_device):
        return True

    def end(self):
        return True

    def updateState(self, new_state):
        dirty_flags = new_state.state()
        if dirty_flags & QPaintEngine.DirtyTransform:
            self._transform = new_state.transform()
        if dirty_flags & QPaintEngine.DirtyOpacity:
            self._opacity = new_state.opacity()
        if dirty_flags & QPaintEngine.DirtyPen:
            self._pen = new_state.pen()
        if (
            dirty_flags & QPaintEngine.DirtyClipEnabled
            or dirty_flags & QPaintEngine.DirtyClipRegion
            or dirty_flags & QPaintEngine.DirtyClipPath
        ):
            if new_state.clipOperation() != Qt.NoClip:
                raise NotImplementedError(
                    "Clipping mode {} not supported".format(new_state.clipOperation())
                )
        if dirty_flags & QPaintEngine.DirtyCompositionMode:
            if new_state.compositionMode() != QPainter.CompositionMode_SourceOver:
                raise NotImplementedError(
                    "CompositionMode {} not supported".format(
                        new_state.compositionMode()
                    )
                )

    def drawImage(self, r, pm, sr, flags):
        self.drawRects(r, 1)

    def drawPixmap(self, r, pm, sr):
        self.drawRects(r, 1)

    def drawPolygon(self, points, count, mode):
        raise NotImplementedError(
            "PyQt5 doesn't have the same handling for polygons."
        )

    def drawPath(self, path):
        if (
            self._pen.style() == Qt.NoPen
            or self._pen.brush().style() == Qt.NoBrush
        ):
            return

        if self._pen.brush().style() == Qt.SolidPattern:
            ri, gi, bi, ai = self._pen.brush().color().getRgb()

            a = self._opacity * (ai / 255)

            rgba = (ri / 255, gi / 255, bi / 255, a)
        else:
            rgba = None

        pen_width = self._pen.widthF() or 1.0
        dash_pattern = [v * pen_width for v in self._pen.dashPattern()]
        dash_offset = self._pen.dashOffset() * pen_width

        transform = self._transform
        inverse_transform, invertable = self._transform.inverted()
        if not invertable:
            transform = inverse_transform = QTransform()
            if dash_pattern:
                warnings.warn(
                    "Dashed lines transformed by non-singular matrices are "
                    "not supported and the dash pattern will be incorrectly "
                    "scaled."
                )

        test_line = QLineF(0, 0, 2**0.5 / 2.0, 2**0.5 / 2.0)
        scaled_pen_width = pen_width * self._transform.map(test_line).length()

        if self._pen.isCosmetic():
            transform = inverse_transform = QTransform()
            scaled_pen_width = pen_width

        for poly in path.toSubpathPolygons(self._transform):
            #line = [p.toTuple() for p in inverse_transform.map(poly)]
            line = [(p.x(), p.y()) for p in inverse_transform.map(poly)]
            sub_lines = dash_line(line, dash_pattern, dash_offset)

            self._outlines.extend(
                (rgba, scaled_pen_width, [transform.map(*p) for p in line])
                for line in sub_lines
            )


class OutlinePaintDevice(QPaintDevice):
    def __init__(self, width_mm, height_mm, pixels_per_mm=5):
        super().__init__()
        self._width = width_mm
        self._height = height_mm
        self._ppmm = pixels_per_mm

        self._paint_engine = OutlinePaintEngine(self)

    def getOutlines(self):
        scale = 1.0 / self._ppmm
        return [
            (rgba, width * scale, [(x * scale, y * scale) for (x, y) in line])
            for (rgba, width, line) in self._paint_engine.getOutlines()
        ]

    def paintEngine(self):
        return self._paint_engine

    def metric(self, num):
        mm_per_inch = 25.4

        if num == QPaintDevice.PdmWidth:
            return self._width * self._ppmm
        elif num == QPaintDevice.PdmHeight:
            return self._height * self._ppmm
        elif num == QPaintDevice.PdmWidthMM:
            return self._width
        elif num == QPaintDevice.PdmHeightMM:
            return self._height
        elif num == QPaintDevice.PdmNumColors:
            return 2
        elif num == QPaintDevice.PdmDepth:
            return 1
        elif num == QPaintDevice.PdmDpiX:
            return mm_per_inch * self._ppmm
        elif num == QPaintDevice.PdmDpiY:
            return mm_per_inch * self._ppmm
        elif num == QPaintDevice.PdmPhysicalDpiX:
            return mm_per_inch * self._ppmm
        elif num == QPaintDevice.PdmPhysicalDpiY:
            return mm_per_inch * self._ppmm
        elif num == QPaintDevice.PdmDevicePixelRatio:
            return 1
        elif num == QPaintDevice.PdmDevicePixelRatioScaled:
            return 1 * self.devicePixelRatioFScale()
        else:
            raise NotImplementedError("Unknown metric {}".format(num))
