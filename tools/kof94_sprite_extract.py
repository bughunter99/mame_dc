"""
kof94 Neo Geo 스프라이트 추출기
================================
roms/kof94.zip 에서 C ROM 데이터를 읽어 스프라이트 타일을 PNG로 저장합니다.

사용법:
  pip install Pillow
  python tools/kof94_sprite_extract.py
  python tools/kof94_sprite_extract.py --tile 0 100       # 타일 0~99 추출
  python tools/kof94_sprite_extract.py --sheet            # 전체 시트 이미지 생성
  python tools/kof94_sprite_extract.py --bank 0 --sheet   # 뱅크0(C1+C2)만 시트 생성

Neo Geo C ROM 포맷 개요:
  - 타일 1개 = 16×16 픽셀, 4bpp (팔레트 인덱스 0~15)
  - C ROM은 쌍으로 동작: C1+C2 = 뱅크0, C3+C4 = 뱅크1, C5+C6 = 뱅크2, C7+C8 = 뱅크3
  - C-홀수(C1,C3,...): 비트플레인 0,1 (하위 2비트)
  - C-짝수(C2,C4,...): 비트플레인 2,3 (상위 2비트)
  - 1바이트 = 4픽셀분 2-비트플레인 데이터 (비트 7~6=픽셀0, 5~4=픽셀1, 3~2=픽셀2, 1~0=픽셀3)
  - 타일당 64바이트(홀수 C) + 64바이트(짝수 C) = 128바이트
"""

import argparse
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Pillow 가 필요합니다: pip install Pillow")

ROM_ZIP = Path(__file__).parent.parent / "roms" / "kof94.zip"
OUTPUT_DIR = Path(__file__).parent.parent / "tools" / "sprites"

# C ROM 파일명 쌍 (홀수, 짝수) × 4 뱅크
C_ROM_PAIRS = [
    ("055-c1.c1", "055-c2.c2"),
    ("055-c3.c3", "055-c4.c4"),
    ("055-c5.c5", "055-c6.c6"),
    ("055-c7.c7", "055-c8.c8"),
]

# 기본 팔레트: 0=투명(흰색), 1~15=연속 색상
# 실제 팔레트는 런타임에 게임이 로드하므로 시각 확인용 근사 팔레트 사용
DEFAULT_PALETTE = [
    (255, 255, 255),   # 0 = 투명 → 흰 배경
    (  0,   0,   0),   # 1 = 검정
    (128,   0,   0),   # 2
    (  0, 128,   0),   # 3
    (  0,   0, 128),   # 4
    (128, 128,   0),   # 5
    (  0, 128, 128),   # 6
    (128,   0, 128),   # 7
    (192,   0,   0),   # 8
    (  0, 192,   0),   # 9
    (  0,   0, 192),   # 10
    (192, 192,   0),   # 11
    (  0, 192, 192),   # 12
    (192,   0, 192),   # 13
    (255, 165,   0),   # 14
    ( 64,  64,  64),   # 15
]


def load_c_rom_pair(zip_path: Path, odd_name: str, even_name: str) -> tuple[bytes, bytes]:
    """zip에서 C ROM 쌍을 읽어 반환."""
    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {e.filename for e in zf.infolist()}
        if odd_name not in names_in_zip or even_name not in names_in_zip:
            raise FileNotFoundError(
                f"C ROM 파일을 찾을 수 없습니다: {odd_name}, {even_name}\n"
                f"zip 내 파일: {sorted(names_in_zip)}"
            )
        c_odd = zf.read(odd_name)
        c_even = zf.read(even_name)
    return c_odd, c_even


def decode_tile(c_odd: bytes, c_even: bytes, tile_index: int) -> list[list[int]]:
    """
    주어진 C ROM 쌍에서 tile_index 번째 타일을 디코딩.
    반환: 16×16 팔레트 인덱스 배열 (0~15)
    """
    base = tile_index * 64  # 타일당 64바이트 (각 C ROM 기준)
    if base + 64 > len(c_odd) or base + 64 > len(c_even):
        raise IndexError(f"타일 인덱스 {tile_index} 범위 초과")

    rows = []
    for row in range(16):
        pixels = []
        for byte_pos in range(4):  # 4바이트 × 4픽셀 = 16픽셀/행
            odd_byte  = c_odd [base + row * 4 + byte_pos]
            even_byte = c_even[base + row * 4 + byte_pos]
            for px in range(4):
                shift = 6 - px * 2
                lo2 = (odd_byte  >> shift) & 0x3   # 비트플레인 0,1
                hi2 = (even_byte >> shift) & 0x3   # 비트플레인 2,3
                pixels.append(lo2 | (hi2 << 2))
        rows.append(pixels)
    return rows


def tile_to_image(tile_data: list[list[int]], palette=None, scale: int = 1) -> Image.Image:
    """팔레트 인덱스 배열 → PIL 이미지 (RGBA, 인덱스0=투명)."""
    pal = palette or DEFAULT_PALETTE
    img = Image.new("RGBA", (16 * scale, 16 * scale))
    pixels = img.load()
    for row_idx, row in enumerate(tile_data):
        for col_idx, idx in enumerate(row):
            r, g, b = pal[idx]
            a = 0 if idx == 0 else 255  # 인덱스 0 = 투명
            for sy in range(scale):
                for sx in range(scale):
                    pixels[col_idx * scale + sx, row_idx * scale + sy] = (r, g, b, a)
    return img


def extract_tiles(
    bank: int = 0,
    tile_start: int = 0,
    tile_end: int | None = None,
    scale: int = 2,
    output_dir: Path = OUTPUT_DIR,
):
    """C ROM 뱅크에서 타일 범위를 개별 PNG로 저장."""
    odd_name, even_name = C_ROM_PAIRS[bank]
    print(f"[로딩] 뱅크{bank}: {odd_name} + {even_name}")
    c_odd, c_even = load_c_rom_pair(ROM_ZIP, odd_name, even_name)

    max_tiles = len(c_odd) // 64
    end = min(tile_end if tile_end is not None else max_tiles, max_tiles)

    out = output_dir / f"bank{bank}"
    out.mkdir(parents=True, exist_ok=True)

    print(f"[추출] 타일 {tile_start}~{end-1} → {out}")
    for i in range(tile_start, end):
        tile_data = decode_tile(c_odd, c_even, i)
        img = tile_to_image(tile_data, scale=scale)
        img.save(out / f"tile_{i:05d}.png")
    print(f"[완료] {end - tile_start}개 저장")


def make_sprite_sheet(
    bank: int = 0,
    tile_start: int = 0,
    tile_count: int = 256,
    cols: int = 32,
    scale: int = 2,
    output_dir: Path = OUTPUT_DIR,
):
    """C ROM 뱅크의 타일들을 하나의 스프라이트 시트 PNG로 저장."""
    odd_name, even_name = C_ROM_PAIRS[bank]
    print(f"[로딩] 뱅크{bank}: {odd_name} + {even_name}")
    c_odd, c_even = load_c_rom_pair(ROM_ZIP, odd_name, even_name)

    max_tiles = len(c_odd) // 64
    actual_count = min(tile_count, max_tiles - tile_start)
    rows_count = (actual_count + cols - 1) // cols

    tile_size = 16 * scale
    sheet = Image.new("RGBA", (cols * tile_size, rows_count * tile_size), (200, 200, 200, 255))

    for i in range(actual_count):
        tile_data = decode_tile(c_odd, c_even, tile_start + i)
        img = tile_to_image(tile_data, scale=scale)
        col = i % cols
        row = i // cols
        sheet.paste(img, (col * tile_size, row * tile_size), img)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"sheet_bank{bank}_{tile_start}_{tile_start+actual_count}.png"
    sheet.save(out_path)
    print(f"[완료] 스프라이트 시트 → {out_path}  ({cols}×{rows_count} = {actual_count}타일)")
    return out_path


def list_banks():
    """각 뱅크의 타일 수를 출력."""
    with zipfile.ZipFile(ROM_ZIP) as zf:
        print(f"\n[{ROM_ZIP.name}] C ROM 뱅크 정보")
        for bank, (odd, even) in enumerate(C_ROM_PAIRS):
            size = zf.getinfo(odd).file_size
            tile_count = size // 64
            print(f"  뱅크{bank}: {odd} + {even}  →  {tile_count:,}타일  ({size/1024/1024:.1f}MB × 2)")


def main():
    parser = argparse.ArgumentParser(description="kof94 스프라이트 추출기")
    parser.add_argument("--bank", type=int, default=0, choices=[0, 1, 2, 3],
                        help="C ROM 뱅크 (0=C1+C2, 1=C3+C4, 2=C5+C6, 3=C7+C8)")
    parser.add_argument("--tile", type=int, nargs=2, metavar=("START", "END"),
                        help="개별 PNG 저장할 타일 범위 (예: --tile 0 100)")
    parser.add_argument("--sheet", action="store_true",
                        help="스프라이트 시트 PNG 1장 생성")
    parser.add_argument("--count", type=int, default=256,
                        help="시트에 포함할 타일 수 (기본: 256)")
    parser.add_argument("--cols", type=int, default=32,
                        help="시트 열 수 (기본: 32)")
    parser.add_argument("--scale", type=int, default=2,
                        help="확대 배수 (기본: 2 → 32×32px)")
    parser.add_argument("--list", action="store_true",
                        help="뱅크별 타일 수만 출력")
    args = parser.parse_args()

    if not ROM_ZIP.exists():
        raise SystemExit(f"ROM 파일 없음: {ROM_ZIP}")

    if args.list:
        list_banks()
        return

    if args.tile:
        extract_tiles(args.bank, args.tile[0], args.tile[1], args.scale)
    elif args.sheet:
        make_sprite_sheet(args.bank, 0, args.count, args.cols, args.scale)
    else:
        # 기본: 각 뱅크 첫 256타일 시트 생성
        list_banks()
        print("\n모든 뱅크 시트 생성 중...")
        for bank in range(4):
            make_sprite_sheet(bank, 0, 256, 32, 2)


if __name__ == "__main__":
    main()
