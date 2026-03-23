#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_CONFIG_PATH = Path(__file__).with_name("organizer_rules.json")
DEFAULT_REPORT_DIR = Path(__file__).with_name("reports")

DOC_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "txt", "md", "html"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ARCHIVE_EXTENSIONS = {"zip", "7z", "rar", "tar", "gz"}
INSTALLER_EXTENSIONS = {"dmg", "pkg"}
CODE_EXTENSIONS = {"sql", "kt", "py", "js", "ts", "tsx", "jsx", "java", "json", "yaml", "yml"}

GENERIC_LABEL_STOPWORDS = {
    "file",
    "files",
    "download",
    "downloads",
    "data",
    "sheet",
    "시트",
    "자료",
    "버전",
    "version",
    "copy",
    "final",
}

NORMALIZE_PATTERNS = [
    re.compile(r"\(\d+\)"),
    re.compile(r"\bcopy\b", re.IGNORECASE),
    re.compile(r"\boriginal\b", re.IGNORECASE),
    re.compile(r"\btextclipping\b", re.IGNORECASE),
    re.compile(r"\b20\d{2}[._ -]?\d{2}[._ -]?\d{2}\b"),
    re.compile(r"\b\d{8}_\d{6}\b"),
    re.compile(r"\b\d{4}\.\d{2}\.\d{2}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{6,14}\b"),
    re.compile(r"\b[ap]m\b", re.IGNORECASE),
    re.compile(r"\b(?:오전|오후)\b"),
    re.compile(r"\bv(?:er)?\.?\d+\b", re.IGNORECASE),
    re.compile(r"\bs\d{3}\b", re.IGNORECASE),
    re.compile(r"\barm64\b", re.IGNORECASE),
    re.compile(r"\baarch64\b", re.IGNORECASE),
    re.compile(r"\bdarwin\b", re.IGNORECASE),
    re.compile(r"\buniversal\b", re.IGNORECASE),
]

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass
class CategoryRule:
    path: tuple[str, str]
    keywords: tuple[str, ...]
    extensions: tuple[str, ...]
    allow_extension_only: bool


@dataclass
class FileEntry:
    source: Path
    relative_name: str
    ext: str
    normalized_title: str
    tokens: tuple[str, ...]
    category_major: str = ""
    category_minor: str = ""
    cluster_label: str = ""
    target_path: Path | None = None


@dataclass
class Cluster:
    major: str
    minor: str
    items: list[FileEntry] = field(default_factory=list)
    token_counter: Counter[str] = field(default_factory=Counter)

    def add(self, entry: FileEntry) -> None:
        self.items.append(entry)
        self.token_counter.update(entry.tokens)

    @property
    def core_tokens(self) -> set[str]:
        if not self.items:
            return set()
        min_count = max(1, math.ceil(len(self.items) * 0.5))
        return {token for token, count in self.token_counter.items() if count >= min_count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize top-level files in a folder into category/subcategory folders using filename heuristics."
    )
    parser.add_argument("--source", type=Path, default=Path.home() / "Downloads", help="Folder to scan. Default: ~/Downloads")
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Root folder to move organized files into. Default: <source>/_sorted_downloads",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="JSON config containing category rules and stopwords.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory where CSV/JSON reports are written.",
    )
    parser.add_argument("--apply", action="store_true", help="Move files. Without this flag, only a dry-run plan is generated.")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.45,
        help="Cluster merge threshold between 0 and 1. Higher means stricter grouping.",
    )
    return parser.parse_args()


def load_config(path: Path) -> tuple[list[CategoryRule], set[str], set[str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rules = [
        CategoryRule(
            path=(item["path"][0], item["path"][1]),
            keywords=tuple(normalize_keyword(keyword) for keyword in item.get("keywords", [])),
            extensions=tuple(ext.lower().lstrip(".") for ext in item.get("extensions", [])),
            allow_extension_only=bool(item.get("allow_extension_only", False)),
        )
        for item in raw["category_rules"]
    ]
    cluster_stopwords = {normalize_keyword(word) for word in raw.get("cluster_stopwords", [])}
    ignore_prefixes = set(raw.get("ignore_prefixes", ["."]))
    return rules, cluster_stopwords, ignore_prefixes


def normalize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def normalize_title(stem: str) -> str:
    text = normalize_keyword(stem)
    text = text.replace("_", " ").replace("-", " ").replace(".", " ").replace("/", " ")
    for pattern in NORMALIZE_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(title: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(title):
        cleaned = token.lower()
        if cleaned.isdigit():
            continue
        if len(cleaned) == 1 and re.match(r"[a-z]", cleaned):
            continue
        tokens.append(cleaned)
    return tuple(tokens)


def scan_files(source: Path, ignore_prefixes: set[str]) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for item in sorted(source.iterdir(), key=lambda path: path.name.lower()):
        if not item.is_file():
            continue
        if any(item.name.startswith(prefix) for prefix in ignore_prefixes):
            continue
        ext = item.suffix.lower().lstrip(".")
        stem = item.stem if ext else item.name
        normalized_title = normalize_title(stem)
        entries.append(
            FileEntry(
                source=item,
                relative_name=item.name,
                ext=ext,
                normalized_title=normalized_title,
                tokens=tokenize(normalized_title),
            )
        )
    return entries


def assign_category(entry: FileEntry, rules: list[CategoryRule]) -> tuple[str, str]:
    haystack = " ".join(entry.tokens)
    best_score = -1
    best_path: tuple[str, str] | None = None

    for index, rule in enumerate(rules):
        keyword_hits = sum(1 for keyword in rule.keywords if keyword and keyword in haystack)
        extension_hit = 1 if entry.ext in rule.extensions else 0
        if keyword_hits == 0 and not (rule.allow_extension_only and extension_hit):
            continue
        score = keyword_hits * 3 + extension_hit
        if score > best_score:
            best_score = score
            best_path = rule.path
            best_index = index
            continue
        if score == best_score and best_path is not None and best_score > 0 and index < best_index:
            best_path = rule.path
            best_index = index

    if best_score > 0 and best_path is not None:
        return best_path

    if entry.ext in INSTALLER_EXTENSIONS:
        return ("소프트웨어", "설치파일")
    if entry.ext in ARCHIVE_EXTENSIONS:
        return ("보관", "압축파일")
    if entry.ext in IMAGE_EXTENSIONS:
        return ("이미지", "사진자료")
    if entry.ext in CODE_EXTENSIONS:
        return ("개발", "코드")
    if entry.ext in DOC_EXTENSIONS:
        return ("문서", "미분류")
    return ("기타", "미분류")


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def cluster_entries(entries: list[FileEntry], cluster_stopwords: set[str], threshold: float) -> list[Cluster]:
    grouped: dict[tuple[str, str], list[FileEntry]] = defaultdict(list)
    for entry in entries:
        grouped[(entry.category_major, entry.category_minor)].append(entry)

    all_clusters: list[Cluster] = []
    for (major, minor), items in grouped.items():
        clusters: list[Cluster] = []
        for entry in sorted(items, key=lambda item: (-len(item.tokens), item.relative_name.lower())):
            best_cluster: Cluster | None = None
            best_score = 0.0
            for cluster in clusters:
                score = jaccard_similarity(entry.tokens, cluster.core_tokens or cluster.token_counter.keys())
                if score > best_score:
                    best_score = score
                    best_cluster = cluster
            if best_cluster is not None and best_score >= threshold:
                best_cluster.add(entry)
            else:
                new_cluster = Cluster(major=major, minor=minor)
                new_cluster.add(entry)
                clusters.append(new_cluster)

        for cluster in clusters:
            label = build_cluster_label(cluster, cluster_stopwords)
            for item in cluster.items:
                item.cluster_label = label
            all_clusters.append(cluster)

    return all_clusters


def build_cluster_label(cluster: Cluster, cluster_stopwords: set[str]) -> str:
    if len(cluster.items) <= 3:
        min_count = len(cluster.items)
    else:
        min_count = max(2, math.ceil(len(cluster.items) * 0.6))
    common_tokens = [
        token
        for token, count in cluster.token_counter.items()
        if count >= min_count and token not in cluster_stopwords and token not in GENERIC_LABEL_STOPWORDS
    ]
    common_tokens.sort(key=lambda token: (-cluster.token_counter[token], token))
    if common_tokens:
        return sanitize_folder_name(" ".join(deduplicate_label_tokens(common_tokens)[:4]))

    fallback_tokens = [
        token
        for token, _ in cluster.token_counter.most_common(4)
        if token not in cluster_stopwords and token not in GENERIC_LABEL_STOPWORDS
    ]
    if fallback_tokens:
        return sanitize_folder_name(" ".join(deduplicate_label_tokens(fallback_tokens)))

    first_title = cluster.items[0].normalized_title or cluster.items[0].source.stem
    return sanitize_folder_name(first_title[:60] or "misc")


def sanitize_folder_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:\*\?\"<>\|]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "misc"


def deduplicate_label_tokens(tokens: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        canonical = token[:-1] if re.fullmatch(r"[a-z]{4,}s", token) else token
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def allocate_target_paths(entries: list[FileEntry], target_root: Path) -> None:
    planned: set[Path] = set()
    for entry in sorted(entries, key=lambda item: item.relative_name.lower()):
        base_dir = target_root / entry.category_major / entry.category_minor / entry.cluster_label
        target = base_dir / entry.relative_name
        if target not in planned and not target.exists():
            entry.target_path = target
            planned.add(target)
            continue

        stem = target.stem
        suffix = target.suffix
        counter = 2
        while True:
            candidate = base_dir / f"{stem} ({counter}){suffix}"
            if candidate not in planned and not candidate.exists():
                entry.target_path = candidate
                planned.add(candidate)
                break
            counter += 1


def write_reports(entries: list[FileEntry], report_dir: Path, applied: bool) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = report_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = run_dir / "file_inventory.csv"
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["original_name", "extension", "normalized_title", "major_category", "minor_category", "cluster_label"])
        for entry in sorted(entries, key=lambda item: item.relative_name.lower()):
            writer.writerow(
                [
                    entry.relative_name,
                    entry.ext,
                    entry.normalized_title,
                    entry.category_major,
                    entry.category_minor,
                    entry.cluster_label,
                ]
            )

    plan_path = run_dir / "move_plan.csv"
    with plan_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["original_name", "target_path", "mode"])
        for entry in sorted(entries, key=lambda item: item.relative_name.lower()):
            writer.writerow([entry.relative_name, str(entry.target_path), "move" if applied else "planned"])

    summary_path = run_dir / "summary.json"
    category_counts: dict[str, int] = Counter(
        f"{entry.category_major}/{entry.category_minor}" for entry in entries
    )
    cluster_counts: dict[str, int] = Counter(
        f"{entry.category_major}/{entry.category_minor}/{entry.cluster_label}" for entry in entries
    )
    summary = {
        "generated_at": datetime.now().isoformat(),
        "applied": applied,
        "file_count": len(entries),
        "category_counts": dict(sorted(category_counts.items())),
        "cluster_counts": dict(sorted(cluster_counts.items())),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def apply_moves(entries: list[FileEntry]) -> None:
    for entry in entries:
        assert entry.target_path is not None
        entry.target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entry.source), str(entry.target_path))


def print_summary(entries: list[FileEntry], report_path: Path, applied: bool) -> None:
    category_counts: Counter[str] = Counter(f"{entry.category_major}/{entry.category_minor}" for entry in entries)
    cluster_counts: Counter[str] = Counter(f"{entry.category_major}/{entry.category_minor}/{entry.cluster_label}" for entry in entries)

    print(f"{'Applied' if applied else 'Planned'} {len(entries)} file moves.")
    print("Top categories:")
    for category, count in category_counts.most_common(10):
        print(f"  - {category}: {count}")
    print("Top clusters:")
    for cluster, count in cluster_counts.most_common(12):
        print(f"  - {cluster}: {count}")
    print(f"Reports: {report_path}")


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")

    target_root = args.target_root.expanduser().resolve() if args.target_root else (source / "_sorted_downloads")
    rules, cluster_stopwords, ignore_prefixes = load_config(args.config.expanduser().resolve())
    entries = scan_files(source, ignore_prefixes)
    if not entries:
        raise SystemExit("No top-level files found to organize.")

    for entry in entries:
        entry.category_major, entry.category_minor = assign_category(entry, rules)

    cluster_entries(entries, cluster_stopwords, args.similarity_threshold)
    allocate_target_paths(entries, target_root)
    report_path = write_reports(entries, args.report_dir.expanduser().resolve(), applied=args.apply)

    if args.apply:
        apply_moves(entries)

    print_summary(entries, report_path, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
