from __future__ import annotations

from pathlib import Path
import re


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


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

        return source_path.read_text(encoding="utf-8").rstrip()

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