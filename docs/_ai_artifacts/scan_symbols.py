"""주석/독스트링/일반 문자열에서 특수기호 사용 위치를 분류 집계.

출력: docs/_ai_artifacts/symbol_report.txt (UTF-8)
분류: COMMENT(# 주석) / DOCSTRING(모듈·클래스·함수 첫 문자열) / STRING(런타임 문자열)
"""
import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SYMBOLS = ["→", "—", "·", "←", "↔", "≥", "±", "->"]
GLOBS = ["app/**/*.py", "pipeline/**/*.py", "tests/**/*.py", "alembic/**/*.py",
         "load_pipeline_outputs.py", "notebooks/**/*.py"]


def docstring_linenos(src: str) -> set[int]:
    """모듈/클래스/함수 docstring이 차지하는 줄 번호 집합."""
    lines = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return lines
    nodes = [tree] + [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for node in nodes:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            c = body[0].value
            for ln in range(c.lineno, c.end_lineno + 1):
                lines.add(ln)
    return lines


def main():
    files = sorted({f for g in GLOBS for f in ROOT.glob(g) if f.is_file()})
    counts = {"COMMENT": 0, "DOCSTRING": 0, "STRING": 0}
    hits = {"COMMENT": [], "DOCSTRING": [], "STRING": []}

    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[SKIP] {f}: {e}")
            continue
        ds_lines = docstring_linenos(src)
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except Exception as e:
            print(f"[SKIP-TOK] {f}: {e}")
            continue
        rel = str(f.relative_to(ROOT))
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                cat = "COMMENT"
            elif tok.type == tokenize.STRING:
                cat = "DOCSTRING" if tok.start[0] in ds_lines else "STRING"
            else:
                continue
            text = tok.string
            found = [s for s in SYMBOLS if s in text]
            if found:
                counts[cat] += 1
                preview = text.replace("\n", "\\n")[:120]
                hits[cat].append(f"{rel}:{tok.start[0]} [{','.join(found)}] {preview}")

    out = [f"== 집계: COMMENT {counts['COMMENT']} / DOCSTRING {counts['DOCSTRING']} / STRING {counts['STRING']} =="]
    for cat in ("COMMENT", "DOCSTRING", "STRING"):
        out.append(f"\n### {cat} ({counts[cat]})")
        out.extend(hits[cat])
    report = ROOT / "docs" / "_ai_artifacts" / "symbol_report.txt"
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"report -> {report}")
    print(out[0])


if __name__ == "__main__":
    main()
