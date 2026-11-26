import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from qrs.data.archive import parse_checksum, parse_listing
from qrs.data.klines import parse_kline_csv, read_kline_zip

LISTING = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<IsTruncated>true</IsTruncated>
<CommonPrefixes><Prefix>data/spot/monthly/klines/AAAUSDT/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/spot/monthly/klines/BBBUSDT/</Prefix></CommonPrefixes>
<Contents><Key>data/x.zip</Key><Size>752</Size></Contents>
</ListBucketResult>"""

ROW_MS = "1640995200000,1,2,0.5,1.5,10,1641081599999,15,7,4,6,0"
ROW_US = "1735689600000000,1,2,0.5,1.5,10,1735775999999999,15,7,4,6,0"


def test_parse_listing_pagination_marker() -> None:
    page = parse_listing(LISTING)
    assert page.prefixes[-1] == "data/spot/monthly/klines/BBBUSDT/"
    assert page.objects[0].size == 752
    assert page.is_truncated
    assert page.next_marker == "data/x.zip"


def test_parse_checksum() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    assert parse_checksum(f"{digest}  FOO-1d-2022-01.zip\n") == digest
    with pytest.raises(ValueError):
        parse_checksum("not-a-digest  file.zip")


def test_timestamps_normalized_to_ms() -> None:
    df = parse_kline_csv(f"{ROW_MS}\n{ROW_US}\n".encode())
    assert df["open_time"].to_list() == [1640995200000, 1735689600000]
    assert df["close_time"].to_list() == [1641081599999, 1735775999999]
    assert "ignore" not in df.columns


def test_csv_with_header() -> None:
    header = "open_time,open,high,low,close,volume,close_time,quote_volume,count,tbb,tbq,ignore"
    df = parse_kline_csv(f"{header}\n{ROW_MS}\n".encode())
    assert df.height == 1
    assert df["quote_volume"][0] == 15.0


def test_read_zip(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AAAUSDT-1d-2022-01.csv", ROW_MS + "\n")
    path = tmp_path / "a.zip"
    path.write_bytes(buf.getvalue())
    assert read_kline_zip(path).height == 1
