"""对比语料库：内存倒排索引 + 句子级相似检索。

参考开源 paper_checking_system（tianlian0）的比对思想——连续公共串超过
阈值即判重——用 n-gram shingle 倒排索引召回候选句，再做精确 containment
比对。文档量在万级以内时内存索引足够快。
"""
import threading
from dataclasses import dataclass

from .. import db
from . import segmenter


@dataclass
class Candidate:
    doc_id: int
    doc_title: str
    sent_idx: int
    sent_text: str
    sim: float


@dataclass
class CorpusDoc:
    doc_id: int
    title: str
    is_builtin: bool
    sentences: list[segmenter.Sentence]


class Corpus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.docs: dict[int, CorpusDoc] = {}
        self.fingerprints: dict[int, int] = {}
        self.inverted: dict[str, list[tuple[int, int]]] = {}

    def rebuild(self) -> None:
        with self._lock:
            self.docs.clear()
            self.inverted.clear()
            self.fingerprints.clear()
            for row in db.all_docs_full():
                did = int(row["id"])
                sents = [
                    s for s in segmenter.split_sentences(row["content"])
                    if s.units >= 4
                ]
                self.docs[did] = CorpusDoc(did, row["title"], bool(row["is_builtin"]), sents)
                from .fingerprint import simhash  # 局部导入避免循环
                norm_all = segmenter.normalize(row["content"], segmenter.detect_language(row["content"]))
                self.fingerprints[did] = simhash(norm_all, segmenter.detect_language(row["content"]))
                for idx, s in enumerate(sents):
                    for sh in segmenter.shingles(s):
                        self.inverted.setdefault(sh, []).append((did, idx))

    def add_and_index(self, doc_id: int) -> None:
        """新文档入索引（增量）。"""
        row = db.get_doc_full(doc_id)
        if row is None:
            return
        with self._lock:
            did = int(row["id"])
            if did in self.docs:
                return
            sents = [
                s for s in segmenter.split_sentences(row["content"])
                if s.units >= 4
            ]
            self.docs[did] = CorpusDoc(did, row["title"], bool(row["is_builtin"]), sents)
            from .fingerprint import simhash
            kind = segmenter.detect_language(row["content"])
            self.fingerprints[did] = simhash(segmenter.normalize(row["content"], kind), kind)
            for idx, s in enumerate(sents):
                for sh in segmenter.shingles(s):
                    self.inverted.setdefault(sh, []).append((did, idx))

    def remove_doc(self, doc_id: int) -> None:
        with self._lock:
            self.docs.pop(doc_id, None)
            self.fingerprints.pop(doc_id, None)
            for key in list(self.inverted):
                self.inverted[key] = [p for p in self.inverted[key] if p[0] != doc_id]
                if not self.inverted[key]:
                    del self.inverted[key]

    def find_similar(self, sent: segmenter.Sentence, threshold: float, top: int = 3) -> list[Candidate]:
        """返回相似度 >= threshold 的候选句，按相似度降序。"""
        sh = segmenter.shingles(sent)
        if not sh:
            return []
        with self._lock:
            # 召回：shingle 命中次数排序
            hits: dict[tuple[int, int], int] = {}
            for s in sh:
                for pos in self.inverted.get(s, ()):  # (doc_id, sent_idx)
                    hits[pos] = hits.get(pos, 0) + 1
            if not hits:
                return []
            ranked = sorted(hits.items(), key=lambda kv: -kv[1])[:200]
            results: list[Candidate] = []
            seen = set()
            for (did, idx), _ in ranked:
                if did in seen:
                    continue
                doc = self.docs.get(did)
                if doc is None:
                    continue
                cand = doc.sentences[idx]
                sim = segmenter.similarity(sh, segmenter.shingles(cand))
                if sim >= threshold:
                    seen.add(did)
                    results.append(Candidate(did, doc.title, idx, cand.text, round(sim, 4)))
                if len(results) >= top:
                    break
            results.sort(key=lambda c: -c.sim)
            return results[:top]

    def stats(self) -> dict:
        with self._lock:
            chars = sum(
                sum(s.units for s in d.sentences) for d in self.docs.values()
            )
            builtin = sum(1 for d in self.docs.values() if d.is_builtin)
            return {
                "documents": len(self.docs),
                "builtin_documents": builtin,
                "sentences": sum(len(d.sentences) for d in self.docs.values()),
                "units": chars,
            }


CORPUS = Corpus()
