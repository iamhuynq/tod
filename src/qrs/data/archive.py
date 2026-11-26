"""Client for the public Binance data archive (data.binance.vision).

Listing uses the S3 bucket API; downloads come from the public CDN and are
verified against the published .CHECKSUM (SHA-256) files.
"""

from __future__ import annotations

import asyncio
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx

LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_URL = "https://data.binance.vision"
_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


class ChecksumMismatchError(RuntimeError):
    """Downloaded file does not match its published SHA-256 checksum."""


@dataclass(frozen=True)
class ArchiveObject:
    key: str
    size: int


@dataclass(frozen=True)
class ListingPage:
    prefixes: list[str]
    objects: list[ArchiveObject]
    is_truncated: bool
    next_marker: str | None


def parse_listing(xml_text: str) -> ListingPage:
    root = ET.fromstring(xml_text)
    prefixes = [
        el.text for el in root.findall("s3:CommonPrefixes/s3:Prefix", _NS) if el.text is not None
    ]
    objects = []
    for el in root.findall("s3:Contents", _NS):
        key = el.findtext("s3:Key", default="", namespaces=_NS)
        size = int(el.findtext("s3:Size", default="0", namespaces=_NS))
        if key:
            objects.append(ArchiveObject(key=key, size=size))
    truncated = root.findtext("s3:IsTruncated", default="false", namespaces=_NS) == "true"
    next_marker = root.findtext("s3:NextMarker", default=None, namespaces=_NS)
    if truncated and next_marker is None:
        last = [*prefixes, *(o.key for o in objects)]
        next_marker = max(last) if last else None
    return ListingPage(prefixes, objects, truncated, next_marker)


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str] | None = None) -> bytes:
    delay = 1.0
    for attempt in range(4):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 404:
                raise FileNotFoundError(url)
            resp.raise_for_status()
            return resp.content
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 3:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


async def list_prefix(
    client: httpx.AsyncClient, prefix: str
) -> tuple[list[str], list[ArchiveObject]]:
    """Return all sub-prefixes and objects directly under `prefix` (handles pagination)."""
    prefixes: list[str] = []
    objects: list[ArchiveObject] = []
    marker: str | None = None
    while True:
        params = {"delimiter": "/", "prefix": prefix}
        if marker:
            params["marker"] = marker
        page = parse_listing((await _get(client, LIST_URL, params)).decode("utf-8"))
        prefixes.extend(page.prefixes)
        objects.extend(page.objects)
        if not page.is_truncated or page.next_marker is None:
            return prefixes, objects
        marker = page.next_marker


def parse_checksum(text: str) -> str:
    """Parse a .CHECKSUM file: '<sha256>  <filename>'."""
    digest = text.strip().split()[0].lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError(f"invalid checksum file content: {text[:80]!r}")
    return digest


async def download_verified(client: httpx.AsyncClient, key: str, dest: Path) -> Path:
    """Download `key` to `dest` unless a verified copy exists. Verifies SHA-256."""
    sidecar = dest.with_name(dest.name + ".sha256")
    if (
        dest.is_file()
        and sidecar.is_file()
        and hashlib.sha256(dest.read_bytes()).hexdigest() == sidecar.read_text().strip()
    ):
        return dest
    expected = parse_checksum((await _get(client, f"{DATA_URL}/{key}.CHECKSUM")).decode())
    payload = await _get(client, f"{DATA_URL}/{key}")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ChecksumMismatchError(f"{key}: expected {expected}, got {actual}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(payload)
    tmp.replace(dest)
    sidecar.write_text(actual + "\n")
    return dest
