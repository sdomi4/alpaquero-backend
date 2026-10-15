"""Coordinate input and presentation; internal RA is hours and Dec is degrees."""
import math
import re
from typing import Literal

Angle = Literal["ra", "dec"]


def parse_coordinate(value: str | float, kind: Angle) -> float:
    text = str(value).strip().translate(str.maketrans({"−": "-", "′": "'", "″": '"'}))
    degrees = bool(re.search(r"[d°]", text, re.I))
    if re.search("h", text, re.I) and (kind == "dec" or degrees):
        raise ValueError("Invalid or mixed coordinate units")
    text = re.sub(r"^d\s*", "", text, flags=re.I)
    number = r"(\d+(?:\.\d*)?|\.\d+)"
    sexagesimal = re.fullmatch(r"([+-]?)(\d+)(?::|\s+)(\d+)(?::|\s+)" + number, text)
    if sexagesimal is None:
        sexagesimal = re.fullmatch(r"([+-]?)(\d+)\s*[hd°]\s*(\d+)\s*[m']\s*" + number + r"\s*[s\"]", text, re.I)
    decimal = r"(\d+(?:\.\d*)?(?:e[+-]?\d+)?|\.\d+(?:e[+-]?\d+)?)"
    match = sexagesimal or re.fullmatch(r"([+-]?)" + decimal + r"\s*[hd°]?", text, re.I)
    if match is None:
        raise ValueError(f"Invalid {kind.upper()}: use decimal, colon-separated, space-separated, or unit-marked coordinates")
    minutes = float(match[3]) if sexagesimal else 0
    seconds = float(match[4]) if sexagesimal else 0
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutes and seconds must be below 60")
    magnitude = float(match[2]) + minutes / 60 + seconds / 3600
    negative = match[1] == "-"
    limit = 90 if kind == "dec" else 360 if degrees else 24
    if not math.isfinite(magnitude) or magnitude > limit or (kind == "ra" and negative):
        raise ValueError("RA must be 0–24 hours (0–360 degrees); Dec must be −90 to +90 degrees")
    result = -magnitude if negative else magnitude
    return ((result / 15 if degrees else result) % 24) if kind == "ra" else result


def parse_pair(text: str) -> tuple[float, float]:
    text = text.strip().replace("−", "-")
    compact = re.fullmatch(r"J(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([+-])(\d{2})(\d{2})(\d{2}(?:\.\d+)?)", text, re.I)
    if compact:
        return (parse_coordinate(f"{compact[1]}:{compact[2]}:{compact[3]}", "ra"),
                parse_coordinate(f"{compact[4]}{compact[5]}:{compact[6]}:{compact[7]}", "dec"))
    candidates = set()
    for separator in re.finditer(r"[,\s]+|(?=[+-])", text):
        try:
            candidates.add((parse_coordinate(text[:separator.start()], "ra"),
                            parse_coordinate(text[separator.end():], "dec")))
        except ValueError:
            pass
    if len(candidates) != 1:
        raise ValueError("Enter a complete, unambiguous RA/Dec pair")
    return candidates.pop()


def parse_coordinates(ra: str | float, dec: str | float) -> tuple[float, float]:
    if not str(dec).strip():
        return parse_pair(str(ra))
    return parse_coordinate(ra, "ra"), parse_coordinate(dec, "dec")


def format_coordinate(value: float, kind: Angle) -> str:
    if not math.isfinite(value):
        raise ValueError("Coordinate must be finite")
    ticks = math.floor(abs(value) * 360000 + 0.5)
    if kind == "ra":
        ticks %= 24 * 360000
    major, remainder = divmod(ticks, 360000)
    minutes, seconds = divmod(remainder, 6000)
    sign = ("-" if math.copysign(1, value) < 0 else "+") if kind == "dec" else ""
    return f"{sign}{major:02d}:{minutes:02d}:{seconds / 100:05.2f}"


def format_coordinates(ra: float, dec: float) -> dict[str, str]:
    return {"ra": format_coordinate(ra, "ra"), "dec": format_coordinate(dec, "dec")}
