from xml.etree import ElementTree

from PyQt5.QtGui import QGuiApplication, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QXmlStreamReader

from svgoutline.svg_utils import (
    namespaces,
    get_svg_page_size,
    lines_polylines_and_polygons_to_paths,
)
from svgoutline.outline_painter import OutlinePaintDevice


# Tell ElementTree to use the conventional namespace aliases for the basic
# namespaces used by SVG. This is not strictly necessary for generating valid
# SVG files but some incorrectly written clients may misbehave (notably Qt's
# QSvg) if these names are not used.
try:
    register_xml_namespace = ElementTree.register_namespace
except AttributeError:

    def register_xml_namespace(prefix, uri):
        ElementTree._namespace_map[uri] = prefix


for prefix, uri in namespaces.items():
    register_xml_namespace(prefix, uri)


def svg_to_outlines(root, width_mm=None, height_mm=None, pixels_per_mm=5.0):
    """
    Given an SVG as a Python ElementTree, return a set of straight line
    segments which approximate the outlines in that SVG when rendered.
    """

    # This method internally uses various parts of Qt which require that a Qt
    # application exists. If one does not exist, one will be created.
    if QGuiApplication.instance() is None:
        QGuiApplication([])  # Pass an empty list for arguments

    # Determine the page size from the document if necessary
    if width_mm is None or height_mm is None:
        width_mm, height_mm = get_svg_page_size(root)

    # Convert all <line>, <polyline> and <polygon> elements to <path>s to
    # work-around PySide bug PYSIDE-891. (See comments in
    # :py:mod:`svgoutline.outline_painter`.).
    root = lines_polylines_and_polygons_to_paths(root)

    # Load the SVG into QSvg
    xml_stream_reader = QXmlStreamReader()
    xml_stream_reader.addData(ElementTree.tostring(root, "unicode"))
    svg_renderer = QSvgRenderer()
    svg_renderer.load(xml_stream_reader)

    # Paint the SVG into the OutlinePaintDevice which will capture the set of
    # line segments which make up the SVG as rendered.
    outline_paint_device = OutlinePaintDevice(width_mm, height_mm, pixels_per_mm)
    painter = QPainter(outline_paint_device)
    try:
        svg_renderer.render(painter)
    finally:
        painter.end()

    return outline_paint_device.getOutlines()
