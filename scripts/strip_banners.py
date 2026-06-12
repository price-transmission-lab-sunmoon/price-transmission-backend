"""배너 주석(# ── ... ──) 줄 일괄 삭제. 삭제 후 연속 공백줄 3개 이상은 2개로 압축.

실행: python scripts/strip_banners.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGET_GLOBS = [
    "app/**/*.py",
    "pipeline/**/*.py",
    "tests/**/*.py",
    "alembic/**/*.py",
    "load_pipeline_outputs.py",
    "notebooks/**/*.py",
]

# U+2500(─) 2개 이상으로 이뤄진 주석 줄 전체
BANNER_RE = re.compile(r"^[ \t]*#[ \t]*─{2,}.*$")


def process_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [SKIP] {path}: read 실패 ({e})")
        return 0

    lines = text.splitlines(keepends=True)
    new_lines = []
    removed = 0
    blank_run = 0

    for line in lines:
        stripped = line.rstrip("\r\n")
        if BANNER_RE.match(stripped):
            removed += 1
            continue
        if stripped.strip() == "":
            blank_run += 1
            if blank_run > 2:
                continue
        else:
            blank_run = 0
        new_lines.append(line)

    if removed > 0:
        try:
            path.write_text("".join(new_lines), encoding="utf-8")
        except Exception as e:
            print(f"  [FAIL] {path}: write 실패 ({e})")
            return 0
    return removed


def main() -> int:
    files = []
    for pattern in TARGET_GLOBS:
        files.extend(ROOT.glob(pattern))
    files = sorted({f for f in files if f.is_file()})

    if not files:
        print("대상 파일 없음 — ROOT 경로 확인 필요:", ROOT)
        return 1

    total = 0
    touched = 0
    for f in files:
        n = process_file(f)
        if n:
            print(f"  {f.relative_to(ROOT)}: {n}")
            total += n
            touched += 1

    print(f"\n배너 {total}줄 삭제 ({touched}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
