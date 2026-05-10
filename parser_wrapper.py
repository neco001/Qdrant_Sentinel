import os
import threading
from typing import Optional

import tree_sitter
import tree_sitter_languages

EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java",
    ".cpp": "cpp", ".c": "c",
}

class LazyParserManager:
    def __init__(self):
        self._local = threading.local()
        self._lang_cache: dict[str, tree_sitter.Language] = {}

    def _get_language(self, ext: str) -> Optional[tree_sitter.Language]:
        lang_name = EXT_TO_LANG.get(ext)
        if not lang_name:
            return None
        if lang_name not in self._lang_cache:
            try:
                self._lang_cache[lang_name] = tree_sitter_languages.get_language(lang_name)
            except Exception:
                return None
        return self._lang_cache[lang_name]

    def _get_parser(self, lang: tree_sitter.Language) -> tree_sitter.Parser:
        if not hasattr(self._local, "parsers"):
            self._local.parsers = {}
        if lang not in self._local.parsers:
            parser = tree_sitter.Parser()
            parser.set_language(lang)
            self._local.parsers[lang] = parser
        return self._local.parsers[lang]

    def parse_file(self, file_path: str, content: str) -> Optional[tree_sitter.Tree]:
        ext = os.path.splitext(file_path)[1].lower()
        lang = self._get_language(ext)
        if not lang:
            return None
        try:
            parser = self._get_parser(lang)
            return parser.parse(content.encode("utf-8"))
        except Exception:
            return None

# Module-level singleton for convenience
_parser_manager = LazyParserManager()

def parse_file(file_path: str, content: str) -> Optional[tree_sitter.Tree]:
    return _parser_manager.parse_file(file_path, content)
