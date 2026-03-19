from pathlib import Path

from prompt_compiler import compile_all_prompts


def main() -> int:
    project_root = Path(__file__).resolve().parent
    compiled_paths = compile_all_prompts(project_root)
    for path in compiled_paths:
        print(path.relative_to(project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())