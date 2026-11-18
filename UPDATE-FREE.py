#!/usr/bin/env python3
"""Carry Blogger Layout settings from an installed XML into a newer Free XML.

Usage: python UPDATE-FREE.py installed-backup.xml new-free.xml updated.xml
The installed XML must be a Blogger Theme > Backup download from the same theme.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET


B = "{http://www.google.com/2005/gml/b}"
WIDGET = re.compile(r"<b:widget\b[^>]*>.*?</b:widget>", re.S)
SETTINGS = re.compile(r"<b:widget-settings\b[^>]*>.*?</b:widget-settings>", re.S)
VARIABLE = re.compile(r"<Variable\b[^>]*/>", re.S)
ATTR = re.compile(r"\b([\w:-]+)\s*=\s*(['\"])(.*?)\2", re.S)


def attributes(tag: str) -> dict[str, str]:
    return {match.group(1): match.group(3) for match in ATTR.finditer(tag)}


def widget_blocks(text: str) -> dict[str, str]:
    found = {}
    for match in WIDGET.finditer(text):
        block = match.group(0)
        widget_id = attributes(block[: block.index(">") + 1]).get("id")
        if widget_id in found:
            raise ValueError(f"Duplicate widget ID: {widget_id}")
        found[widget_id] = block
    return found


def section_for_widgets(root: ET.Element) -> dict[str, str]:
    return {
        widget.get("id"): section.get("id")
        for section in root.iter(B + "section")
        for widget in section.findall(B + "widget")
    }


def replace_attribute(tag: str, name: str, value: str) -> str:
    # Preserve the new theme's tag and renderer attributes; copy only user-facing settings.
    pattern = re.compile(r"(\b" + re.escape(name) + r"\s*=\s*)(['\"])(.*?)\2", re.S)
    if not pattern.search(tag):
        return tag
    return pattern.sub(lambda m: m.group(1) + m.group(2) + value + m.group(2), tag, count=1)


def merge(installed: str, current: str) -> str:
    old_root, new_root = ET.fromstring(installed), ET.fromstring(current)
    old_widgets, new_widgets = widget_blocks(installed), widget_blocks(current)
    old_sections = section_for_widgets(old_root)
    new_widget_sections = section_for_widgets(new_root)
    new_sections = {section.get("id") for section in new_root.iter(B + "section")}
    old_types = {w.get("id"): w.get("type") for w in old_root.iter(B + "widget")}
    new_types = {w.get("id"): w.get("type") for w in new_root.iter(B + "widget")}

    for widget_id, old_block in old_widgets.items():
        if widget_id not in new_widgets:
            section_id = old_sections.get(widget_id)
            if section_id not in new_sections:
                raise ValueError(f"Cannot retain {widget_id}: section {section_id} is missing")
            # An extra user gadget must be reviewed instead of silently discarded.
            raise ValueError(f"Extra gadget {widget_id} in {section_id}; update manually")
        if old_types[widget_id] != new_types[widget_id]:
            raise ValueError(f"Gadget type changed for {widget_id}; update manually")
        if old_sections[widget_id] != new_widget_sections[widget_id]:
            raise ValueError(f"Gadget {widget_id} moved to another section; update manually")

    for widget_id, new_block in new_widgets.items():
        old_block = old_widgets.get(widget_id)
        if old_block is None:
            continue
        old_tag = old_block[: old_block.index(">") + 1]
        new_tag = new_block[: new_block.index(">") + 1]
        old_attrs = attributes(old_tag)
        for name in ("title", "visible"):
            if name in old_attrs:
                new_tag = replace_attribute(new_tag, name, old_attrs[name])
        merged_block = new_tag + new_block[len(new_block[: new_block.index(">") + 1]) :]
        old_settings = SETTINGS.search(old_block)
        if old_settings:
            if SETTINGS.search(merged_block):
                merged_block = SETTINGS.sub(lambda _: old_settings.group(0), merged_block, count=1)
            else:
                merged_block = merged_block.replace(new_tag, new_tag + old_settings.group(0), 1)
        current = current.replace(new_block, merged_block, 1)

    old_values = {}
    for match in VARIABLE.finditer(installed):
        attrs = attributes(match.group(0))
        if "name" in attrs and "value" in attrs:
            old_values[attrs["name"]] = attrs["value"]

    def keep_variable(match: re.Match[str]) -> str:
        tag = match.group(0)
        name = attributes(tag).get("name")
        return replace_attribute(tag, "value", old_values[name]) if name in old_values else tag

    current = VARIABLE.sub(keep_variable, current)
    merged_root = ET.fromstring(current)
    merged_ids = {w.get("id") for w in merged_root.iter(B + "widget")}
    if not set(old_widgets).issubset(merged_ids):
        raise ValueError("Some installed gadgets are missing from the output")
    return current


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    old_path, new_path, out_path = map(Path, sys.argv[1:])
    if out_path.resolve() in {old_path.resolve(), new_path.resolve()}:
        raise SystemExit("Choose a separate output file; never overwrite your backup or release XML")
    merged = merge(old_path.read_text(encoding="utf-8-sig"), new_path.read_text(encoding="utf-8-sig"))
    out_path.write_text(merged, encoding="utf-8", newline="\n")
    print(f"Saved {out_path}")
