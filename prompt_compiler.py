from __future__ import annotations

import argparse
from pathlib import Path
import re
import io
import tokenize


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


def _strip_python_comments(source: str) -> str:
    """Remove Python comment tokens while preserving executable code."""
    reader = io.StringIO(source).readline
    all_tokens = list(tokenize.generate_tokens(reader))
    trivia_tokens = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
    code_lines = {tok.start[0] for tok in all_tokens if tok.type not in trivia_tokens}
    comment_only_lines = {
        tok.start[0]
        for tok in all_tokens
        if tok.type == tokenize.COMMENT and tok.start[0] not in code_lines
    }

    tokens: list[tokenize.TokenInfo] = []

    for tok in all_tokens:
        if tok.type == tokenize.COMMENT:
            continue
        tokens.append(tok)

    stripped = tokenize.untokenize(tokens)
    cleaned_lines = []
    for line_number, line in enumerate(stripped.splitlines(), start=1):
        if line_number in comment_only_lines and not line.strip():
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def compile_prompt_text(prompt_text: str, project_root: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        relative_path = match.group(1)
        source_path = (project_root / relative_path).resolve()

        try:
            source_path.relative_to(project_root.resolve())
        except ValueError as exc:
            raise ValueError(f"Placeholder path escapes project root: {relative_path}") from exc

        if not source_path.is_file():
            raise FileNotFoundError(f"Placeholder source not found: {relative_path}")

        source_text = source_path.read_text(encoding="utf-8")
        if source_path.suffix == ".py":
            source_text = _strip_python_comments(source_text)
        return source_text.rstrip()

    return PLACEHOLDER_PATTERN.sub(replace, prompt_text)


def compile_prompt_file(prompt_path: Path, project_root: Path, output_root: Path) -> Path:
    compiled_text = compile_prompt_text(prompt_path.read_text(encoding="utf-8"), project_root)
    output_path = output_root / prompt_path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(compiled_text, encoding="utf-8")
    return output_path


def compile_all_prompts(
    project_root: Path,
    prompts_dir: Path | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    prompts_dir = prompts_dir or project_root / "prompts"
    output_dir = output_dir or prompts_dir / "compiled"

    output_dir.mkdir(parents=True, exist_ok=True)

    compiled_paths = []
    for prompt_path in sorted(prompts_dir.glob("*.txt")):
        compiled_paths.append(compile_prompt_file(prompt_path, project_root, output_dir))
    return compiled_paths


def main() -> int:
    project_root = Path(__file__).resolve().parent
    compiled_paths = compile_all_prompts(project_root)
    for path in compiled_paths:
        print(path.relative_to(project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())