from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path):
	with path.open("r", encoding="utf-8") as handle:
		for line in handle:
			line = line.strip()
			if line:
				yield json.loads(line)


def load_json(path: Path):
	return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
	return " ".join(text.lower().replace("_", " ").split())


def contains_all_terms(texts: list[str], terms: list[str]) -> bool:
	joined = "\n".join(texts)
	normalized = normalize(joined)
	return all(term in normalized for term in terms)


def version_key(value: str | None) -> tuple[int, int]:
	if not value or "." not in value:
		return (0, 0)
	major, minor = value.split(".", 1)
	try:
		return (int(major), int(minor))
	except ValueError:
		return (0, 0)


def build_base_dir(script_path: Path) -> Path:
	return script_path.resolve().parent.parent / "references" / "touchdesigner_kb"


def search_entities(base_dir: Path, terms: list[str], limit: int):
	results = []
	for record in load_jsonl(base_dir / "version_compatibility.jsonl"):
		texts = [
			str(record.get("entity_name", "")),
			str(record.get("source_title", "")),
			str(record.get("family", "")),
			str(record.get("entity_type", "")),
			str(record.get("compatibility_summary", "")),
			" ".join(record.get("categories", [])),
		]
		if contains_all_terms(texts, terms):
			results.append(record)
	return results[:limit]


def search_families(base_dir: Path, terms: list[str], limit: int):
	results = []
	for record in load_jsonl(base_dir / "family_compatibility.jsonl"):
		texts = [
			str(record.get("family", "")),
			str(record.get("introduced_in_build", "")),
			str(record.get("channel", "")),
			str(record.get("evidence_text", "")),
		]
		if contains_all_terms(texts, terms):
			results.append(record)
	return results[:limit]


def search_chunks(base_dir: Path, terms: list[str], limit: int):
	results = []
	for record in load_jsonl(base_dir / "chunks.jsonl"):
		texts = [
			str(record.get("title", "")),
			str(record.get("page_type", "")),
			str(record.get("text", "")),
			" ".join(record.get("heading_path", [])),
			" ".join(record.get("categories", [])),
		]
		if contains_all_terms(texts, terms):
			results.append(record)
			if len(results) >= limit:
				break
	return results


def search_documents(base_dir: Path, terms: list[str], limit: int):
	results = []
	for record in load_jsonl(base_dir / "documents.jsonl"):
		texts = [
			str(record.get("title", "")),
			str(record.get("source_title", "")),
			str(record.get("page_type", "")),
			str(record.get("summary", "")),
			str(record.get("text", "")),
			" ".join(record.get("categories", [])),
		]
		if contains_all_terms(texts, terms):
			results.append(record)
			if len(results) >= limit:
				break
	return results


def search_assets(base_dir: Path, terms: list[str], limit: int):
	results = []
	for record in load_jsonl(base_dir / "assets_high_value.jsonl"):
		texts = [
			str(record.get("asset_name", "")),
			str(record.get("extension", "")),
			str(record.get("source_url", "")),
			str(record.get("local_path", "")),
		]
		if contains_all_terms(texts, terms):
			results.append(record)
	return results[:limit]


def filter_by_version(records: list[dict], target_version: str) -> list[dict]:
	target_key = version_key(target_version)
	filtered = []
	for record in records:
		introduced = record.get("introduced_in_build") or record.get("family_introduced_in_build")
		introduced_key = version_key(str(introduced) if introduced else None)
		if introduced_key == (0, 0) or introduced_key <= target_key:
			filtered.append(record)
	return filtered


def summarize_stats(base_dir: Path):
	return load_json(base_dir / "stats.json")


def parse_args():
	parser = argparse.ArgumentParser()
	parser.add_argument("dataset", choices=["entities", "families", "chunks", "documents", "assets", "stats"])
	parser.add_argument("terms", nargs="*", help="查询关键词，多个词按 AND 处理")
	parser.add_argument("--limit", type=int, default=10)
	parser.add_argument("--target-version")
	return parser.parse_args()


def main():
	args = parse_args()
	base_dir = build_base_dir(Path(__file__))
	terms = [normalize(term) for term in args.terms if normalize(term)]
	if args.dataset == "stats":
		print(json.dumps(summarize_stats(base_dir), ensure_ascii=False, indent=2))
		return
	searchers = {
		"entities": search_entities,
		"families": search_families,
		"chunks": search_chunks,
		"documents": search_documents,
		"assets": search_assets,
	}
	results = searchers[args.dataset](base_dir, terms, args.limit)
	if args.target_version and args.dataset in {"entities", "families"}:
		results = filter_by_version(results, args.target_version)
	print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
